#!/usr/bin/env python3

import importlib.util
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
        source_pack = Path(
            "/Users/austen/Library/Application Support/Steam/steamapps/workshop/content/325610/1934544571/1-1212scripts.pack"
        )
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
        source_pack = Path(
            "/Users/austen/Library/Application Support/Steam/steamapps/workshop/content/325610/1934544571/1-1212scripts.pack"
        )
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
