# Release checks

Run these commands from the `message-from-aliens-mcp` project directory on
Windows x64 with uv installed.
The examples use PowerShell. Publication requires a PyPI account; local checks
do not.

## Compatibility

Each command builds and installs the package in an isolated environment, rather
than relying on the developer's virtual environment. Run the dependency floor
and the current dependency set:

```powershell
uv run --isolated --no-project --python 3.10 --with . --with "mcp==1.30.0" --with "frida==17.26.2" --with "pillow==10.0.0" --with "windows-capture==2.0.1" python -B -m unittest discover -s tests -q
uv run --isolated --no-project --python 3.12 --with . python -B -m unittest discover -s tests -q
```

Verified on 2026-11-14; all 112 tests passed in each environment:

| Python | MCP SDK | Frida | Pillow | windows-capture |
| --- | --- | --- | --- | --- |
| 3.10.8 | 1.30.0 | 17.26.2 | 10.0.0 | 2.0.1 |
| 3.12.11 | 2.3.0 | 17.26.3 | 13.0.0 | 2.0.1 |

Eleven JavaScript binding/style/annotation/timer/protocol tests use Node when available and are skipped otherwise;
Node is not a server dependency. The SDK 1.x and 2.x adapters are both exercised.
Versions before MCP 1.30 are
outside the supported range: checks with 1.2.0, 1.12.0, and 1.13.0 failed to
import with the currently resolved Pydantic version. Dependency major versions
are bounded so future major releases receive compatibility checks first.

Unit tests check rendering, validation, cache behavior, lifecycle handling, and
MCP output using simulated game data. They do not prove that Frida input or
Windows.Graphics.Capture works on every Windows installation or game build.

## Build and inspect

Keep the version in `pyproject.toml` and `src/aliens_mcp/__init__.py` in sync.
Use a new version for every new PyPI release.

```powershell
uv build --no-sources
$version = "0.1.11"
uvx twine check "dist/message_from_aliens_mcp-${version}-py3-none-any.whl" "dist/message_from_aliens_mcp-${version}.tar.gz"
```

Inspect both the wheel and source archive before publishing. The wheel must
include all eleven files in `aliens_mcp/game/scripts/`, including `protocol.js`
and `exports.js`. The load order is declared in `game/transport.py`. Neither archive should include saves, player
annotations, game assets, generated dumps, or local investigation artifacts.
Confirm the wheel metadata and README contain no placeholders or private paths.

Test the actual wheel with both executable names:

```powershell
$releaseWheel = (Resolve-Path "dist/message_from_aliens_mcp-${version}-py3-none-any.whl").Path
uvx --from $releaseWheel message-from-aliens-mcp --help
uvx --from $releaseWheel aliens-mcp --help
```

Connect an MCP client to the local wheel before uploading. Use `command: "uvx"`
and `args: ["--from", "<absolute wheel path>", "message-from-aliens-mcp"]`.
Check that initialization succeeds and `tools/list` advertises exactly
`launch_game`, `look`, `click`, `note`, `wait`, and `glyph`.

## Game integration

For a new game build or changes to the Frida/capture implementation, verify on
the actual game as well:

1. Read the table, verify an unchanged second result, then request `force=True`.
2. Capture an occluded game window; check colors and physical pixel dimensions.
3. Inspect one current hash using all three glyph formats.
4. Click a known navigation character with the game unfocused and confirm the
   target label and resulting page. Inspect a fresh table before each click.
5. Temporarily change an annotation, check matching occurrences, and restore it.
6. Check a known external link returns its URL without opening a browser.
7. When an exit test is intended, verify the result reports closure and
   `launch_game` reconnects successfully.
8. On the incremental minigame page, skip a short interval with `wait`; verify
   production changes, upgrade counts stay unchanged, and the result is saved.
   Back up progress before this test. On other pages, verify rejection without
   changing timers. Glyph PNGs should be exactly 64x64, including dense glyphs.

## Publish

Create and verify a [PyPI account](https://pypi.org/account/register/), enable
two-factor authentication, and configure a publishing identity. For local
uploads, uv accepts a PyPI API token through `UV_PUBLISH_TOKEN`. Keep tokens out
of the repository, command arguments, logs, and chat. GitHub Actions releases
can use PyPI Trusted Publishing instead.

After the local checks, upload only the intended version:

```powershell
uv publish "dist/message_from_aliens_mcp-${version}-py3-none-any.whl" "dist/message_from_aliens_mcp-${version}.tar.gz"
```

Then verify the public installation independently of the source checkout:

```powershell
uvx "message-from-aliens-mcp==${version}" --help
```

See the official [uv publishing guide](https://docs.astral.sh/uv/guides/package/)
and [PyPI publishing documentation](https://docs.pypi.org/publishing/publishing-to-pypi/).
