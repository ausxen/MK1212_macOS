#!/usr/bin/env python3

import importlib.util
import argparse
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SOURCE = Path(__file__).with_name("mk1212_mac_tool.py")
if not SOURCE.is_file():
    SOURCE = Path(__file__).resolve().parents[1] / "src/mk1212_mac_tool.py"
SPEC = importlib.util.spec_from_file_location("mk1212_mac_tool", SOURCE)
tool = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = tool
SPEC.loader.exec_module(tool)


def dds_header(width, height, mips, fourcc=b"\0\0\0\0", rgb_bits=32, pf_flags=0x41):
    header = bytearray(128)
    header[:4] = b"DDS "
    struct.pack_into("<I", header, 4, 124)
    struct.pack_into("<6I", header, 8, 0xA1007 if mips > 1 else 0x81007,
                     height, width, width * 4, 0, mips if mips > 1 else 0)
    struct.pack_into("<2I", header, 76, 32, pf_flags)
    header[84:88] = fourcc
    struct.pack_into("<I", header, 88, rgb_bits)
    struct.pack_into("<4I", header, 92, 0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000)
    struct.pack_into("<I", header, 108, 0x401008 if mips > 1 else 0x1000)
    return bytes(header)


def write_pack(path, members, pack_type=3):
    encoded = [(name.encode("utf-8"), data) for name, data in members]
    index_bytes = sum(4 + len(name) + 1 for name, _ in encoded)
    body = bytearray(struct.pack("<4s5I", b"PFH4", pack_type, 0, 0, len(encoded), index_bytes))
    body.extend(struct.pack("<I", 0))
    for name, data in encoded:
        body.extend(struct.pack("<I", len(data)))
        body.extend(name + b"\0")
    for _, data in encoded:
        body.extend(data)
    path.write_bytes(body)


class DDSTests(unittest.TestCase):
    def test_uncompressed_missing_mips_are_synthesized(self):
        width, height = 8, 4
        raw = bytes((i % 251 for i in range(width * height * 4)))
        source = dds_header(width, height, 1) + raw
        lower_data = dds_header(width, height, 4) + raw + bytes(4 * 2 * 4 + 2 * 1 * 4 + 1 * 1 * 4)
        lower = tool.parse_dds(lower_data)
        transformed, reason = tool.transform_dds(source, lower)
        info = tool.parse_dds(transformed)
        self.assertEqual((info.width, info.height, info.mip_count), (8, 4, 4))
        self.assertEqual(tool.split_dds_levels(transformed, info)[0], raw)
        self.assertIn("1 mips -> 8x4/4", reason)

    def test_dxt1_two_x_promotion_can_fill_final_block_mips(self):
        source_block = b"\x00\x00\xff\xff" + (0xE4E4E4E4).to_bytes(4, "little")
        source = dds_header(4, 4, 1, b"DXT1", 0, 0x4) + source_block
        lower = tool.parse_dds(dds_header(8, 8, 4, b"DXT1", 0, 0x4) + bytes(32 + 8 + 8 + 8))
        transformed, _ = tool.transform_dds(source, lower)
        info = tool.parse_dds(transformed)
        self.assertEqual((info.width, info.height, info.mip_count), (8, 8, 4))

    def test_real_dxt1_chain_can_be_promoted(self):
        # A complete 4x4 chain has three 8-byte BC1 levels.
        block = b"\x00\x00\xff\xff" + (0xE4E4E4E4).to_bytes(4, "little")
        source = dds_header(4, 4, 3, b"DXT1", 0, 0x4) + block * 3
        lower = tool.parse_dds(dds_header(8, 8, 4, b"DXT1", 0, 0x4) + bytes(56))
        transformed, _ = tool.transform_dds(source, lower)
        info = tool.parse_dds(transformed)
        levels = tool.split_dds_levels(transformed, info)
        self.assertEqual((info.width, info.height, info.mip_count), (8, 8, 4))
        self.assertEqual(levels[1:], [block, block, block])


class ManifestTests(unittest.TestCase):
    def test_manifest_preserves_no_final_newline(self):
        raw = b"a.pack\t1\nb.pack\t2"
        updated = tool.replace_manifest_entries(raw, {"a.pack"}, [("c.pack", 3)])
        self.assertEqual(updated, b"b.pack\t2\nc.pack\t3")
        self.assertFalse(updated.endswith(b"\n"))


class LoadOrderTests(unittest.TestCase):
    def test_explicit_order_preserves_names_and_comments(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "order.txt"
            path.write_text("# highest listed first\nTweaks.pack\n\nSmoke.pack\n", encoding="utf-8")
            self.assertEqual(tool.load_order_names(path), ["Tweaks.pack", "Smoke.pack"])

    def test_explicit_order_rejects_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "order.txt"
            path.write_text("Smoke.pack\nsmoke.PACK\n", encoding="utf-8")
            with self.assertRaises(tool.ToolError):
                tool.load_order_names(path)


class TransientProfileTests(unittest.TestCase):
    def test_new_submod_combination_uses_visible_progress(self):
        with tempfile.TemporaryDirectory() as directory:
            state_dir = Path(directory)
            done_path = state_dir / "done.json"
            state = {
                "game_root": directory,
                "source_packs": [{"name": "one.pack", "path": "/one.pack"}],
                "profiles": {},
            }
            expected = {"key": "prepared-profile"}
            with patch.object(tool, "profile_key", return_value="new-key"), \
                 patch.object(tool, "start_rebuild_progress_window", return_value=done_path), \
                 patch.object(tool, "ensure_profile", return_value=expected) as prepare, \
                 patch.object(tool.time, "sleep"):
                profile = tool.ensure_profile_with_progress(
                    state_dir, state, ["one.pack"],
                )

            self.assertIs(profile, expected)
            self.assertIsNotNone(prepare.call_args.kwargs["progress"])
            self.assertEqual(json.loads(done_path.read_text())["status"], "success")

    def test_fresh_launch_prepares_state_with_visible_progress(self):
        with tempfile.TemporaryDirectory() as directory:
            state_dir = Path(directory)
            done_path = state_dir / "done.json"

            def fake_install(args):
                tool.save_json(Path(args.state_dir) / "state.json", {"status": "prepared"})

            args = argparse.Namespace(game_root=None)
            with patch.object(tool, "start_rebuild_progress_window", return_value=done_path), \
                 patch.object(tool, "install_command", side_effect=fake_install), \
                 patch.object(tool.time, "sleep"):
                state = tool.prepare_launch_state(args, state_dir)

            self.assertEqual(state["status"], "prepared")
            self.assertEqual(json.loads(done_path.read_text())["status"], "success")

    def test_uninstall_is_idempotent_after_cache_was_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            state_dir = Path(directory)
            tool.save_json(state_dir / "state.json", {"status": "uninstalled"})
            with patch.object(tool, "game_running", return_value=False):
                tool.uninstall_command(argparse.Namespace(state_dir=str(state_dir)))

    def test_native_picker_returns_drag_order_and_selection(self):
        state = {
            "source_packs": [
                {"name": "one.pack", "optional": True},
                {"name": "two.pack", "optional": True},
            ],
            "selected_optional_packs": ["one.pack"],
        }
        returned = json.dumps({
            "action": "confirm", "selected": ["two.pack"],
            "order": ["two.pack", "one.pack"],
        })
        with patch.object(tool, "launcher_gui_path", return_value=Path("/tmp/gui")), \
             patch.object(tool.subprocess, "run",
                          return_value=tool.subprocess.CompletedProcess([], 0, returned, "")) as run:
            choice = tool.choose_optional_packs(state, "Launch")
        self.assertEqual(choice, {
            "action": "confirm", "selected": ["two.pack"],
            "order": ["two.pack", "one.pack"],
        })
        config = json.loads(run.call_args.args[0][1])
        self.assertEqual([item["name"] for item in config["items"]], ["one.pack", "two.pack"])
        self.assertIn("Do not enable any mods", config["helpText"])

    def test_force_rebuild_removes_only_generated_profiles(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game = root / "game"
            cache = game / "TotalWarAttilaData/.mk1212-cache"
            profiles = cache / "profiles"
            recovery = cache / "recovery"
            profiles.mkdir(parents=True)
            recovery.mkdir()
            (profiles / "old-generated-file").write_text("generated")
            (recovery / "preserved-file").write_text("preserved")
            state_dir = root / "state"
            state = {
                "game_root": str(game), "cache_root": str(cache),
                "profiles": {"old": {}}, "default_profile_key": "old",
                "core_profile_key": "old",
            }
            with patch.object(tool, "report_rebuild_progress"), \
                 patch.object(tool, "rebuild_profiles_for_current_sources") as rebuild:
                tool.force_rebuild_profile_cache(state_dir, state)
            self.assertFalse(profiles.exists())
            self.assertEqual((recovery / "preserved-file").read_text(), "preserved")
            self.assertEqual(state["profiles"], {})
            self.assertNotIn("default_profile_key", state)
            self.assertNotIn("core_profile_key", state)
            rebuild.assert_called_once_with(state_dir, state)

    def test_nested_gui_app_is_detected_from_its_executable(self):
        executable = Path("/tmp/MK1212 Launcher UI.app/Contents/MacOS/mk1212-launcher-gui")
        self.assertEqual(tool.launcher_gui_app(executable),
                         Path("/tmp/MK1212 Launcher UI.app"))
        self.assertIsNone(tool.launcher_gui_app(Path("/tmp/mk1212-launcher-gui")))

    def test_progress_window_receives_status_and_done_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            state_dir = Path(directory)
            with patch.object(tool, "launcher_gui_path", return_value=Path("/tmp/gui")), \
                 patch.object(tool.subprocess, "Popen") as popen:
                done_path = tool.start_rebuild_progress_window(state_dir)
            config = json.loads((state_dir / "rebuild-progress-ui-config.json").read_text())
            self.assertEqual(config["mode"], "progress")
            self.assertEqual(config["progressPath"], str(state_dir / "rebuild-progress.json"))
            self.assertEqual(config["donePath"], str(done_path))
            popen.assert_called_once()

    def test_progress_reporting_never_posts_system_notification(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(tool.Path, "home", return_value=root), \
                 patch.object(tool.subprocess, "run") as run:
                tool.report_rebuild_progress(root / "state", "Preparing", notify=True)
            run.assert_not_called()
            self.assertTrue((root / "state/rebuild-progress.json").is_file())

    def test_supported_executable_passes_launch_preflight(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game_root = root / "game"
            executable = game_root / tool.EXECUTABLE_RELATIVE
            executable.parent.mkdir(parents=True)
            executable.write_bytes(b"supported executable fixture")
            state_dir = root / "state"
            tool.save_json(state_dir / "state.json", {
                "status": "prepared", "game_root": str(game_root),
            })
            args = argparse.Namespace(game_root=None)
            with patch.object(
                tool, "sha256_path", return_value=tool.SUPPORTED_RUNTIME_EXECUTABLE_SHA256
            ):
                detected_path, digest = tool.preflight_launch_executable(args, state_dir)
            self.assertEqual(detected_path, executable.resolve())
            self.assertEqual(digest, tool.SUPPORTED_RUNTIME_EXECUTABLE_SHA256)

    def test_unknown_executable_hash_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            game_root = Path(directory)
            executable = game_root / tool.EXECUTABLE_RELATIVE
            executable.parent.mkdir(parents=True)
            executable.write_bytes(b"unknown executable fixture")
            with patch.object(tool, "sha256_path", return_value="f" * 64):
                with self.assertRaises(tool.UnsupportedGameExecutableError) as raised:
                    tool.validate_supported_game_executable(game_root)
            self.assertEqual(raised.exception.path, executable)
            self.assertEqual(raised.exception.detected_sha256, "f" * 64)

    def test_unsupported_executable_stops_before_setup_activation_or_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game_root = root / "game"
            executable = game_root / tool.EXECUTABLE_RELATIVE
            executable.parent.mkdir(parents=True)
            executable.write_bytes(b"updated executable fixture")
            state_dir = root / "state"
            tool.save_json(state_dir / "state.json", {
                "status": "prepared", "game_root": str(game_root),
            })
            args = argparse.Namespace(
                state_dir=str(state_dir), game_root=None,
                core_only=False, no_picker=False,
            )
            with patch.object(tool, "game_running", return_value=False), \
                 patch.object(tool, "sha256_path", return_value="e" * 64), \
                 patch.object(tool, "show_native_error") as show_error, \
                 patch.object(tool, "prepare_launch_state") as prepare, \
                 patch.object(tool, "activate_profile") as activate, \
                 patch.object(tool, "prepare_isolated_home") as isolated_home, \
                 patch.object(tool.subprocess, "Popen") as popen:
                with self.assertRaises(tool.NativeErrorDisplayed):
                    tool.launch_command(args)
            prepare.assert_not_called()
            activate.assert_not_called()
            isolated_home.assert_not_called()
            popen.assert_not_called()
            self.assertEqual(show_error.call_args.kwargs["title"], "ATTILA has been updated")
            self.assertIn("has not been modified", show_error.call_args.kwargs["message"])

    def test_missing_executable_has_distinct_user_facing_error(self):
        missing = Path("/missing/game") / tool.EXECUTABLE_RELATIVE
        with self.assertRaises(tool.MissingGameExecutableError) as raised:
            tool.validate_supported_game_executable(Path("/missing/game"))
        presentation = tool.executable_error_presentation(raised.exception)
        self.assertEqual(presentation["title"], "ATTILA could not be found")
        self.assertNotIn("updated", presentation["message"].casefold())
        self.assertIn(str(missing), presentation["detail"])

    def test_unsupported_error_presentation_includes_supported_build_and_detail_hash(self):
        error = tool.UnsupportedGameExecutableError(Path("/game/ATTILA"), "d" * 64)
        presentation = tool.executable_error_presentation(error)
        self.assertEqual(presentation["title"], "ATTILA has been updated")
        self.assertIn("480285.103778", presentation["message"])
        self.assertIn("stopped rather than applying", presentation["message"])
        self.assertIn("d" * 64, presentation["detail"])

    def test_executable_hashing_error_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            game_root = Path(directory)
            executable = game_root / tool.EXECUTABLE_RELATIVE
            executable.parent.mkdir(parents=True)
            executable.write_bytes(b"unreadable executable fixture")
            with patch.object(tool, "sha256_path", side_effect=OSError("read failed")):
                with self.assertRaises(tool.GameExecutableVerificationError):
                    tool.validate_supported_game_executable(game_root)

    def test_stale_activation_is_recovered_before_executable_preflight(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state_dir = root / "state"
            game_root = root / "game"
            tool.save_json(state_dir / "state.json", {
                "status": "prepared", "game_root": str(game_root),
            })
            tool.save_json(state_dir / "activation.json", {"id": "stale"})
            order = []

            def recover(*_args):
                order.append("recover")

            def validate(root_arg):
                order.append("validate")
                return root_arg / tool.EXECUTABLE_RELATIVE, tool.SUPPORTED_RUNTIME_EXECUTABLE_SHA256

            with patch.object(tool, "recover_stale_activation", side_effect=recover), \
                 patch.object(tool, "validate_supported_game_executable", side_effect=validate):
                tool.preflight_launch_executable(argparse.Namespace(game_root=None), state_dir)
            self.assertEqual(order, ["recover", "validate"])

    def test_workshop_source_change_still_uses_existing_rebuild_flow(self):
        records = [{"name": "updated.pack"}]
        state = {"source_packs": records}
        with patch.object(tool, "changed_source_records", return_value=records), \
             patch.object(tool, "confirm_source_rebuild", return_value=True) as confirm, \
             patch.object(tool, "rebuild_profiles_for_current_sources") as rebuild:
            self.assertTrue(tool.rebuild_changed_workshop_sources_for_launch(
                Path("/state"), state
            ))
        confirm.assert_called_once_with(records)
        rebuild.assert_called_once_with(Path("/state"), state)

    def test_native_error_helper_receives_error_mode_configuration(self):
        with patch.object(tool, "launcher_gui_path", return_value=Path("/tmp/gui")), \
             patch.object(
                 tool.subprocess, "run",
                 return_value=tool.subprocess.CompletedProcess([], 0, "", ""),
             ) as run:
            tool.show_native_error("ATTILA has been updated", "Stopped safely", "hash")
        config = json.loads(run.call_args.args[0][1])
        self.assertEqual(config["mode"], "error")
        self.assertEqual(config["errorTitle"], "ATTILA has been updated")
        self.assertEqual(config["errorMessage"], "Stopped safely")
        self.assertEqual(config["errorDetail"], "hash")

    def test_refresh_discovers_new_workshop_pack_without_feral_record(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pack = root / "Tycherious' 4TPY Updated Event Timing 2.0.pack"
            write_pack(pack, [("campaigns/test.lua", b"return true")], pack_type=3)
            state = {"game_root": str(root), "source_packs": []}
            with patch.object(tool, "inventory_packs", return_value={pack.name.casefold(): [pack]}), \
                 patch.object(tool, "feral_mod_records", return_value=[]):
                self.assertEqual(tool.refresh_optional_sources(state), [pack.name])
            self.assertEqual(state["source_packs"][0]["name"], pack.name)
            self.assertTrue(state["source_packs"][0]["optional"])

    def test_refresh_appends_new_pack_after_legacy_optional_order(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pack = root / "new-submod.pack"
            write_pack(pack, [("campaigns/test.lua", b"return true")], pack_type=3)
            state = {"game_root": str(root), "source_packs": [
                {"name": "existing-submod.pack", "optional": True},
            ]}
            with patch.object(tool, "inventory_packs",
                              return_value={pack.name.casefold(): [pack]}), \
                 patch.object(tool, "feral_mod_records", return_value=[]):
                self.assertEqual(tool.refresh_optional_sources(state), [pack.name])
            self.assertEqual(tool.optional_load_order(state),
                             ["existing-submod.pack", pack.name])

    def test_safe_destination_rejects_traversal_and_absolute_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for unsafe in ("../escape", "a/../../escape", "/absolute", r"C:\\escape"):
                with self.subTest(unsafe=unsafe), self.assertRaises(tool.ToolError):
                    tool.safe_destination(root, unsafe)

    def test_safe_destination_keeps_generated_path_under_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(tool.safe_destination(root, "script/campaign/file.lua"),
                             root / "script/campaign/file.lua")

    def test_optional_selection_preserves_authoritative_source_order(self):
        state = {"source_packs": [
            {"name": "core-a.pack", "optional": False},
            {"name": "submod-high.pack", "optional": True},
            {"name": "core-b.pack", "optional": False},
            {"name": "submod-low.pack", "optional": True},
        ]}
        self.assertEqual(
            tool.selected_names(state, ["submod-low.pack", "submod-high.pack"]),
            ["submod-high.pack", "submod-low.pack", "core-a.pack", "core-b.pack"],
        )
        self.assertEqual(tool.selected_names(state, []), ["core-a.pack", "core-b.pack"])

    def test_optional_selection_uses_persisted_load_order(self):
        state = {"source_packs": [
            {"name": "core-a.pack", "optional": False},
            {"name": "submod-high.pack", "optional": True},
            {"name": "submod-low.pack", "optional": True},
            {"name": "core-b.pack", "optional": False},
        ], "optional_load_order": ["submod-low.pack", "submod-high.pack"]}
        self.assertEqual(
            tool.selected_names(state, ["submod-high.pack", "submod-low.pack"]),
            ["submod-low.pack", "submod-high.pack", "core-a.pack", "core-b.pack"],
        )

    def test_profile_records_follow_selected_load_order(self):
        state = {"source_packs": [
            {"name": "core.pack", "optional": False},
            {"name": "submod-low.pack", "optional": True},
            {"name": "submod-high.pack", "optional": True},
        ]}
        records = tool.records_for_names(
            state, ["submod-high.pack", "submod-low.pack", "core.pack"]
        )
        self.assertEqual(
            [record["name"] for record in records],
            ["submod-high.pack", "submod-low.pack", "core.pack"],
        )

    def test_optional_load_order_appends_new_packs_without_reordering_existing(self):
        state = {"source_packs": [
            {"name": "submod-a.pack", "optional": True},
            {"name": "submod-b.pack", "optional": True},
            {"name": "submod-new.pack", "optional": True},
        ], "optional_load_order": ["submod-b.pack", "submod-a.pack"]}
        self.assertEqual(tool.optional_load_order(state),
                         ["submod-b.pack", "submod-a.pack", "submod-new.pack"])

    def test_profile_key_changes_with_source_selection(self):
        first = {"name": "core.pack", "sha256": "a" * 64}
        optional = {"name": "submod.pack", "sha256": "b" * 64}
        self.assertNotEqual(tool.profile_key([first]), tool.profile_key([first, optional]))

    def test_profile_key_changes_with_compatibility_revision(self):
        record = {"name": "core.pack", "sha256": "a" * 64}
        self.assertNotEqual(tool.profile_key([record], "before"),
                            tool.profile_key([record], "after"))

    def test_feral_faction_layout_preserves_child_bounds(self):
        original = (b"before\n"
                    b"faction_details_parent_uic:Resize(436, 616);\n"
                    b"middle\n"
                    b"faction_details_parent_uic:Resize(436, 616);\n"
                    b"after\n")
        patched, repairs = tool.apply_lua_compatibility(
            "lua_scripts/frontend_scripted.lua", original
        )
        self.assertEqual(patched.count(b"Resize(436, 616, false)"), 2)
        self.assertNotIn(b"Resize(436, 616);", patched)
        self.assertEqual(len(repairs), 1)

    def test_feral_custom_battle_popup_preserves_child_bounds_and_alignment(self):
        original = (b"if popup_menu_uic and popup_menu_uic:Visible() then\n"
                    b"\t\t\t\t\t\t\ttm:callback(\n"
                    b"popup_menu_uic:Resize((225 * num_columns), (30 * max_rows) + 12);\n"
                    b"\t\t\t\t\t\t\t\t\t\t\t--popup_menu_uic:SetMoveable(true);\n"
                    b"\t\t\t\t\t\t\t\t\t\t\t--popup_menu_uic:MoveTo(popup_menuX - ((boundsX * num_columns) / 2), popup_menuY);\n"
                    b"\t\t\t\t\t\t\t\t\t\t\t--popup_menu_uic:SetMoveable(false);\n"
                    b"\n"
                    b"\t\t\t\t\t\t\t\t\t\t\tpopup_listX, popup_listY = popup_list_uic:Position(); -- Reset pos.\n"
                    b"uic:SetMoveable(false);\n"
                    b"\t\t\t\t\t\t\t\t\t\t\t\tuic:SetVisible(true);\n"
                    b"\t\t\t\t\t\t\t\t\t\t\tend\n")
        patched, repairs = tool.apply_lua_compatibility(
            "lua_scripts/frontend_scripted.lua", original
        )
        self.assertIn(
            b"popup_menu_uic:Resize((225 * num_columns), (30 * max_rows) + 12, false);",
            patched,
        )
        self.assertNotIn(
            b"popup_menu_uic:Resize((225 * num_columns), (30 * max_rows) + 12);",
            patched,
        )
        self.assertIn(b"Keep the pre-resize popup-list origin on Feral", patched)
        self.assertNotIn(b"popup_listX, popup_listY = popup_list_uic:Position(); -- Reset pos.", patched)
        self.assertNotIn(b"popup_menu_uic:MoveTo(", patched)
        self.assertNotIn(b"popup_menuX - ((boundsX * num_columns) / 2)", patched)
        self.assertEqual(patched.count(b"popup_list_uic:SetVisible(false);"), 1)
        self.assertEqual(patched.count(b"popup_list_uic:SetVisible(true);"), 1)
        self.assertEqual(len(repairs), 1)

    def test_macos_slot_helper_ui_is_removed_but_listener_entry_point_remains(self):
        source_pack = (Path.home() /
            "Library/Application Support/Steam/steamapps/workshop/content/325610/1934544571/1-1212scripts.pack")
        if not source_pack.is_file():
            self.skipTest("local MK1212 Scripts pack is unavailable")
        _, entries = tool.read_pack(source_pack)
        entry = next(
            item for item in entries
            if item.relative_path.casefold() == "campaigns/main_attila/mk1212_slots.lua"
        )
        with source_pack.open("rb") as stream:
            original = tool.read_entry(stream, entry)
        patched, repairs = tool.apply_lua_compatibility(entry.relative_path, original)
        self.assertIn(b'function Add_MK1212_Slots_Listeners()', patched)
        self.assertIn(b'UIComponent(button_found):SetVisible(false)', patched)
        self.assertNotIn(b'CreateComponent', patched)
        self.assertNotIn(b'ComponentLClickUp', patched)
        self.assertNotIn(b'SimulateClick', patched)
        self.assertNotIn(b'MK1212_10slots.exe', patched)
        self.assertNotIn(b'os.execute', patched)
        self.assertEqual(len(repairs), 1)

    def test_frontend_windows_helper_prompt_is_not_constructed(self):
        source_pack = (Path.home() /
            "Library/Application Support/Steam/steamapps/workshop/content/325610/1934544571/1-1212scripts.pack")
        if not source_pack.is_file():
            self.skipTest("local MK1212 Scripts pack is unavailable")
        _, entries = tool.read_pack(source_pack)
        entry = next(item for item in entries
                     if item.relative_path.casefold() == "lua_scripts/frontend_disclaimer.lua")
        with source_pack.open("rb") as stream:
            original = tool.read_entry(stream, entry)
        patched, repairs = tool.apply_lua_compatibility(entry.relative_path, original)
        self.assertNotIn(b'CreateComponent', patched)
        self.assertNotIn(b'add_listener', patched)
        self.assertNotIn(b'MK1212_10slots.exe', patched)
        self.assertEqual(len(repairs), 1)

    def test_appdata_paths_are_left_unchanged_pending_a_b_test(self):
        source = (
            b'\tlocal army_setups_path = os.getenv("APPDATA")..[[\\The Creative Assembly\\Attila\\army_setups\\]];\n'
            b'\tlocal battle_preferences_path = os.getenv("APPDATA")..[[\\The Creative Assembly\\Attila\\battle_preferences\\]];'
        )
        patched, repairs = tool.apply_lua_compatibility(
            "lua_scripts/frontend_cb_crash_fix.lua", source
        )
        self.assertEqual(patched, source)
        self.assertEqual(repairs, [])

    def test_hre_logging_is_left_unchanged_pending_a_b_test(self):
        source = (
            b'    local logFilePath = "C:\\\\Users\\\\mitch\\\\AppData\\\\Roaming\\\\The Creative Assembly\\\\Attila\\\\logs\\\\mitch_debug_log.txt"\n'
            b'    local file = io.open(logFilePath, "a")'
        )
        patched, repairs = tool.apply_lua_compatibility(
            "campaigns/main_attila/mechanics/hre/mechanics_hre.lua", source
        )
        self.assertEqual(patched, source)
        self.assertEqual(repairs, [])

    def test_discord_command_is_left_unchanged_pending_a_b_test(self):
        source = b'\tos.execute("start https://discord.com/invite/WzbeUxR");'
        patched, repairs = tool.apply_lua_compatibility(
            "lua_scripts/frontend_discord.lua", source
        )
        self.assertEqual(patched, source)
        self.assertEqual(repairs, [])

    def test_hre_ui_is_left_unchanged_pending_a_b_test(self):
        source = (
            b'settlement_captured_uic:Resize(settlement_captured_uicbX - 275, settlement_captured_uicbY);\n'
            b'button_parent_uic:Resize(button_parent_uicbX - 275, button_parent_uicbY);\n'
            b'panReformsView:Resize(545, 300);\n'
        )
        patched, repairs = tool.apply_lua_compatibility(
            "campaigns/main_attila/mechanics/hre/mechanics_hre_ui.lua", source
        )
        self.assertEqual(patched, source)
        self.assertEqual(repairs, [])

    def test_decisions_ui_is_left_unchanged_until_tested(self):
        source = (
            b'mapParchment:Resize(sizeX + 120, sizeY + 100);\n'
            b'mapParchmentPanel:Resize(sizeX + 120, sizeY + 100);\n'
        )
        patched, repairs = tool.apply_lua_compatibility(
            "campaigns/main_attila/mechanics/decisions/mechanics_decisions_ui.lua", source
        )
        self.assertEqual(patched, source)
        self.assertEqual(repairs, [])

    def test_first_pack_remains_loose_lua_winner(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "TotalWarAttilaData/data").mkdir(parents=True)
            high, low = root / "high.pack", root / "low.pack"
            write_pack(high, [("script/shared.lua", b"high")])
            write_pack(low, [("script/shared.lua", b"low")])
            _, winners = tool.plan_compatibility(root, [high, low])
            self.assertEqual(winners["script/shared.lua"][0], high)

    def test_high_priority_pack_gets_later_movie_filename(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "TotalWarAttilaData/data").mkdir(parents=True)
            high, low = root / "high.pack", root / "low.pack"
            write_pack(high, [("campaigns/main_attila/startpos.esf", b"high")])
            write_pack(low, [("campaigns/main_attila/startpos.esf", b"low")])
            plan, _ = tool.plan_compatibility(root, [high, low])
            self.assertEqual([item["order"] for item in plan], [1, 2])
            self.assertEqual([item["autoload_order"] for item in plan], [2, 1])
            self.assertGreater(plan[0]["content_name"], plan[1]["content_name"])

    def test_mod_dds_is_checked_against_stock_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "TotalWarAttilaData/data").mkdir(parents=True)
            high = root / "high.pack"
            stock = root / "TotalWarAttilaData/data/models.pack"
            high_dds = dds_header(4, 4, 3) + bytes(4 * 4 * 4 + 2 * 2 * 4 + 1 * 1 * 4)
            stock_dds = dds_header(8, 8, 4) + bytes(8 * 8 * 4 + 4 * 4 * 4 + 2 * 2 * 4 + 1 * 1 * 4)
            write_pack(high, [("textures/shared.dds", high_dds)])
            write_pack(stock, [("textures/shared.dds", stock_dds)], pack_type=4)
            plan, _ = tool.plan_compatibility(root, [high])
            self.assertEqual(len(plan[0]["repairs"]), 1)
            self.assertGreater(plan[0]["overlay_name"], plan[0]["content_name"])
            repaired = tool.parse_dds(plan[0]["repairs"][0]["data"])
            self.assertEqual((repaired.width, repaired.height, repaired.mip_count), (8, 8, 4))

    def test_mod_to_mod_dds_difference_is_not_rewritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "TotalWarAttilaData/data").mkdir(parents=True)
            high, low = root / "high.pack", root / "low.pack"
            high_dds = dds_header(4, 4, 3) + bytes(4 * 4 * 4 + 2 * 2 * 4 + 1 * 1 * 4)
            low_dds = dds_header(8, 8, 4) + bytes(8 * 8 * 4 + 4 * 4 * 4 + 2 * 2 * 4 + 1 * 1 * 4)
            write_pack(high, [("textures/shared.dds", high_dds)])
            write_pack(low, [("textures/shared.dds", low_dds)])
            plan, _ = tool.plan_compatibility(root, [high, low])
            self.assertEqual([len(item["repairs"]) for item in plan], [0, 0])


class NativeClonePatchTests(unittest.TestCase):
    def test_native_clone_gets_only_a_sibling_data_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state_dir = root / "shim-state"
            clone_root = state_dir / "native-clone"
            clone_root.mkdir(parents=True)
            data_root = root / "Steam game" / "TotalWarAttilaData"
            data_directory = data_root / "data"
            data_directory.mkdir(parents=True)
            state = {"data_root": str(data_directory)}
            link = tool.ensure_native_clone_data_link(state_dir, state)
            self.assertTrue(link.is_symlink())
            self.assertEqual(link.resolve(), data_root.resolve())
            self.assertEqual(link.parent, clone_root)

    def test_native_clone_patch_changes_only_guarded_instructions(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "Total War ATTILA"
            executable.touch()
            with executable.open("r+b") as stream:
                for item in tool.NATIVE_SLOT_PATCHES:
                    stream.seek(item["file_offset"] - 4)
                    stream.write(item["before_context"])
            applied = tool.patch_native_clone(executable)
            self.assertEqual(len(applied), 2)
            with executable.open("rb") as stream:
                for item in tool.NATIVE_SLOT_PATCHES:
                    stream.seek(item["file_offset"] - 4)
                    self.assertEqual(stream.read(len(item["after_context"])), item["after_context"])

    def test_native_clone_patch_refuses_wrong_preimage_without_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "Total War ATTILA"
            executable.touch()
            first, second = tool.NATIVE_SLOT_PATCHES
            with executable.open("r+b") as stream:
                stream.seek(first["file_offset"] - 4)
                stream.write(first["before_context"])
                stream.seek(second["file_offset"] - 4)
                stream.write(bytes(len(second["before_context"])))
            with self.assertRaises(tool.ToolError):
                tool.patch_native_clone(executable)
            with executable.open("rb") as stream:
                stream.seek(first["file_offset"] - 4)
                self.assertEqual(stream.read(len(first["before_context"])), first["before_context"])


if __name__ == "__main__":
    unittest.main()
