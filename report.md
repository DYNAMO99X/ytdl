# Analysis Report: ytdl TUI Search Bug

## TL;DR
YouTube search is broken in the TUI because **all 4 nested message handlers in `tui.py` use the wrong handler names**. Textual 8 dispatches nested-message handlers using the qualified class namespace, but the code uses short names. Result: the `SearchResultsMsg` and `SearchErrorMsg` (and `ProgressMsg`/`LogMsg`) never reach their handlers. The TUI silently does nothing — no error, no rows.

This was verified empirically by patching the handlers with the correct names (`on_main_screen_search_results_msg`, `on_download_screen_progress_msg`, etc.) — search then populates 20 rows correctly.

---

## Files Inspected
All project files (excluding `.venv`, `.git`, `*.egg-info`):
- `pyproject.toml`, `requirements.txt`, `ytdl`, `.gitignore`
- `src/ytdl/__init__.py`, `__main__.py`, `cli.py`, `core.py`, `config.py`, `display.py`, `shortcuts.py`, **`tui.py`**

## Environment
- Python 3.12, Textual **8.2.7** (installed in `~/.local/lib/`)
- `.venv` is **empty** (no packages installed)
- `yt-dlp` is available on `$PATH`
- CLI commands all work; only the TUI is broken

---

## Root Cause — Textual 8 Message Handler Naming

In Textual 8, when a `Message` subclass is **defined inside another class**, the dispatcher computes the handler name from the **qualified class name**, not just the inner class name. Source (`textual/message.py`):

```python
qualname = cls.__qualname__.rsplit("<locals>.", 1)[-1]
namespace = qualname.rsplit(".", 2)[-2:]   # keeps last two parts
name = "_".join(camel_to_snake(part) for part in namespace)
cls.handler_name = f"on_{name}"
```

So for a class declared as:
```python
class MainScreen(Screen):
    class SearchResultsMsg(Message): ...
```
…Textual sets `SearchResultsMsg.handler_name = "on_main_screen_search_results_msg"`.

Verified directly:
```
SearchResultsMsg handler: on_main_screen_search_results_msg
SearchErrorMsg handler:   on_main_screen_search_error_msg
ProgressMsg handler:      on_download_screen_progress_msg
LogMsg handler:           on_download_screen_log_msg
```

### The 4 broken handlers in `src/ytdl/tui.py`

| Line | Defined method | Textual actually calls |
|---|---|---|
| 274 | `DownloadScreen.on_progress_msg` | `on_download_screen_progress_msg` |
| 312 | `DownloadScreen.on_log_msg` | `on_download_screen_log_msg` |
| 593 | `MainScreen.on_search_results_msg` | `on_main_screen_search_results_msg` |
| 615 | `MainScreen.on_search_error_msg` | `on_main_screen_search_error_msg` |

Because no method matches, the message arrives at `_on_message` (logged it directly), dispatch finds nothing, the message is silently dropped, and the UI never updates. `post_message` doesn't raise — Textual just logs `method=None` at verbose level and moves on.

### Why it manifests as "search not working"
1. User types query → presses Enter / clicks Search
2. `MainScreen._do_search()` → `_run_search()` starts a daemon thread
3. Thread runs `ytdl.core.search()` (works fine — yt-dlp returns JSON)
4. Thread calls `self.app.call_from_thread(self.post_message, SearchResultsMsg(...))` (succeeds)
5. **Message is dispatched, but no handler exists → table stays empty, no error surfaced to user**

The CLI's `search` command works because it uses synchronous `_run_ytdlp()` + Rich tables, no Textual messages involved.

---

## Reproduction (verified)

```python
async with app.run_test(...) as pilot:
    si.value = "lofi music"
    await pilot.click("#search-btn")
    await pilot.pause(20)
    print(table.row_count)  # → 0  (with the bug)
```

After monkey-patching `MainScreen.on_main_screen_search_results_msg` to the correct name, `row_count` becomes **20** with all rows populated (verified live).

---

## Fixes Required (for your reference — not applied)

Two reasonable options, both simple:

**Option A — Rename the four methods** in `tui.py`:
- `on_progress_msg` → `on_download_screen_progress_msg`
- `on_log_msg` → `on_download_screen_log_msg`
- `on_search_results_msg` → `on_main_screen_search_results_msg`
- `on_search_error_msg` → `on_main_screen_search_error_msg`

**Option B — Lift the message classes out of their parent classes** to module level (or at least define them with explicit `namespace=` parameter to `__init_subclass__`). Then the current method names work as-is.

Option A is the smallest change.

---

## Other Findings (lower priority)

While scanning, I noted these — none break search, but you may want to look at them:

1. **`pyproject.toml` / `requirements.txt` don't list `yt-dlp`.** The README says it's "already installed on your system", but the wrapper shells out to `yt-dlp` directly. If someone installs `ytdl` cleanly in a fresh venv, every command crashes with `RuntimeError: yt-dlp not found`. Consider adding `yt-dlp` to `dependencies`.

2. **`.venv` is empty.** You have it in `.gitignore` (good), but `pip install -r requirements.txt` won't auto-activate it. `pip install -e .` will install into it, but nothing has been installed yet. Whatever Python you actually run with needs textual available — works because of the user-site install.

3. **`tui.py:157–159` — `SearchResultScreen.compose()`** uses `Static(... f"Views: {self.video.view_count:,}" if ...)` — order-of-operations bug: the `f"..."` ends before `if`, so the conditional applies to the *outer* `Static(...)` call, not the formatted string. Likely fine in practice (defaults to empty string), but the conditional logic is wrong. Should be `Static((f"Views: {self.video.view_count:,}" if self.video.view_count else ""), ...)`.

4. **`tui.py:447–461` — `_save_config()` in `ConfigScreen`** iterates `for key in list(config.keys()):` and queries `#cfg-{key}`. But the General/Formats/Advanced tabs only display a subset of keys (e.g. `subtitles_lang`, `concurrent_fragments`, etc.). For any key whose input field was never created (because it's not in the displayed subset, or it's missing from defaults), `self.query_one(f"#cfg-{key}", Input)` raises `NoMatches`, crashing the Save button. Specifically fragile keys not in the displayed lists: `proxy`, `cookies_file`, `limit_rate`, `retries`, `subtitles`, `subtitles_lang`, etc. — clicking **Save** on the Config screen will raise and the try/except in `on_button_pressed` would surface it as an unhandled exception.

5. **`tui.py:285–306` — `_run_download`** — this is a `@work(thread=True)` decorated method, but it calls `self.post_message(...)`. With Textual's `@work(thread=True)`, the code runs on a worker thread, so `self.post_message` is the right way to talk back. **However**, since this method's handlers (`on_progress_msg`, `on_log_msg`) are also misnamed, the progress screen is also silently broken — same bug, same fix.

6. **`tui.py:582–589` — `MainScreen._run_search`** uses raw `threading.Thread`. Other places use `@work(thread=True)` (e.g. `DownloadScreen._run_download`). Inconsistent, both work, but the inconsistent style is unusual. Also `_run_download` doesn't `await` — it's defined `async def` but never awaits anything inside, then `post_message` is called from the worker thread, which is fine for `@work(thread=True)` but worth noting.

7. **`tui.py:152` — `SearchResultScreen` is never wired up for viewing search results** (the only place that pushes it is `_show_selected_info` — fine), but the screen imports `VideoInfo`, `format_filesize`, etc. that aren't all used (some unused imports — cosmetic).

8. **`core.py:288` — `parse_destination_line` is defined in `tui.py` but a near-duplicate logic exists in `core.py:_extract_output_path`.** The TUI re-implements path extraction. Not a bug, but the logic differs (TUI uses regex, core uses both regex and fallback scan). Minor risk of drift.

9. **`cli.py:153` — `download_cmd`** has `task = progress.add_task(...)` but never references `task` again afterwards. Dead code (cosmetic).

10. **`core.py:188` — `search()`** has a hard-coded `timeout=30`. Long searches will fail with `RuntimeError("yt-dlp timed out")` and the TUI shows a generic "Search failed: yt-dlp timed out" toast. May want a longer timeout or streamed/async search.

---

## Recommended Action (when you want to fix it)

Apply **Option A** (rename 4 methods). The diff would be ~4 lines:

```diff
-    def on_progress_msg(self, event: ProgressMsg) -> None:
+    def on_download_screen_progress_msg(self, event: ProgressMsg) -> None:
```
…and the same pattern for the other three handlers.

That single change should make the search tab fully functional (and also fix the per-download progress/log messages in `DownloadScreen`).