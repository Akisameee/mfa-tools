"""Style geometry and color matching without a running game."""

import shutil
import subprocess
import unittest
from pathlib import Path


@unittest.skipUnless(shutil.which("node"), "Node is needed for JavaScript style checks")
class RenderedStyleTests(unittest.TestCase):
    def test_snapshot_and_click_use_only_rendered_outlines(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [
                shutil.which("node"),
                str(root / "tests/decoration_capture_fixture.js"),
                str(root / "src/aliens_mcp/game/scripts"),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def check_style(self, assertions):
        source = (
            Path(__file__).resolve().parents[1]
            / "src/aliens_mcp/game/scripts/decorations.js"
        )
        program = (
            """
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const context = vm.createContext({});
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), context);
const {underlineAt, sameColor, rectangleBounds, gridFrames, frameAt} = context;
"""
            + assertions
        )
        result = subprocess.run(
            [shutil.which("node"), "-e", program, str(source)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_real_underline_segments_and_spans_exclude_other_rows_and_shapes(self):
        self.check_style("""
const p = {x: 0.5, y: 4.75, z: 0};
const segment = [{x: 0.05, y: 3.8299999, z: 0}, {x: 4, y: 3.8299999, z: 0}];
assert.equal(underlineAt(p, [segment]), true);
assert.equal(underlineAt({...p, x: 3.5}, [[segment[1], segment[0]]]), true);
assert.equal(underlineAt({...p, x: 4.5}, [segment]), false);
assert.equal(underlineAt({...p, y: 3.25}, [segment]), false);
assert.equal(underlineAt(p, [[segment[0], {...segment[1], y: 3}]]), false);
assert.equal(underlineAt(p, [[{x: 0, y: 4.25, z: 0}, {x: 1, y: 4.25, z: 0}]]), false);
assert.equal(underlineAt(p, [[segment[0], segment[0]]]), false);
assert.equal(underlineAt(null, [segment]), false);
""")

    def test_dim_colors_use_current_palette_with_float_tolerance(self):
        self.check_style("""
const dim = [0.4, 0.36, 0.28, 1];
assert.equal(sameColor([0.400000006, 0.359999985, 0.280000001, 1], dim), true);
assert.equal(sameColor([1, 0.9, 0.7, 1], dim), false);
assert.equal(sameColor([0.4, 0.36, 0.28, 0.25], dim), false);
assert.equal(sameColor(null, dim), false);
""")

    def test_closed_axis_aligned_rectangles_are_distinct_from_underlines(self):
        self.check_style("""
const p = (x, y, z = 0) => ({x, y, z});
const points = [p(1, 5), p(0, 5), p(0, 2), p(1, 2), p(1, 5)];
assert.equal(JSON.stringify(rectangleBounds(points)),
             JSON.stringify({left: 0, right: 1, bottom: 2, top: 5, z: 0}));
assert.ok(rectangleBounds([...points].reverse()));
assert.equal(rectangleBounds(points.slice(0, 2)), null);
assert.equal(rectangleBounds([...points.slice(0, 4), p(1, 4)]), null);
assert.equal(rectangleBounds([p(1, 5), p(0, 4), p(0, 2), p(1, 2), p(1, 5)]), null);
assert.equal(rectangleBounds(points.map((v, i) => i === 2 ? {...v, z: 1} : v)), null);
assert.equal(rectangleBounds(points.map(v => ({...v, x: 0}))), null);
assert.equal(rectangleBounds([...points.slice(0, 4), null]), null);
assert.equal(underlineAt(p(0.5, 5.92), []), false);
""")

    def test_card_frames_map_complete_grid_regions_including_empty_slots(self):
        self.check_style("""
const positions = [];
for (let col = 14; col < 17; col++) for (let row = 1; row < 4; row++)
    positions.push({row, col, x: col - 13.5, y: 4.75 - (row - 1) * 1.5, z: 0});
const rect = {left: 0, right: 1, top: 5.25, bottom: 2.25, z: 0};
const frames = gridFrames([rect, rect, {...rect, left: 1, right: 2}], positions);
assert.equal(JSON.stringify(frames), '[[1,14,2,14],[1,15,2,15]]');
assert.equal(JSON.stringify(frameAt(1, 14, frames)),
             JSON.stringify({top: true, bottom: false, left: true, right: true}));
assert.equal(frameAt(3, 14, frames), null);
assert.equal(frameAt(1, 14, [[1,14,1,14]]), null);
assert.equal(JSON.stringify(gridFrames([{...rect, z: 1}], positions)), '[]');
// A missing grid transform must not invent a larger contiguous frame.
assert.equal(JSON.stringify(gridFrames([{...rect, right: 2}], positions.slice(1))), '[]');
""")
