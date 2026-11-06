"""Browser -> built Vue -> real HTTP API -> SQLite. No mocked draft API."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

from playwright.async_api import async_playwright, expect


async def run(base: str) -> dict:
    async with async_playwright() as playwright:
        executable = os.environ.get("VT055_CHROMIUM_EXECUTABLE")
        browser = await playwright.chromium.launch(
            headless=True, **({"executable_path": executable} if executable else {})
        )
        context = await browser.new_context()
        context.set_default_timeout(10_000)
        first = await context.new_page()

        async def snapshot():
            response = await context.request.get(f"{base}/api/pointcloud/pc_e2e/draft")
            assert response.status == 200
            return await response.json()

        await first.goto(f"{base}/viewer/pc_e2e")
        slider = first.get_by_role("slider")
        await expect(slider).to_be_enabled()

        async def edit(page, value):
            await page.get_by_role("slider").evaluate(
                "(el, value) => { el.value = value; el.dispatchEvent(new Event('input', {bubbles:true})); }",
                str(value),
            )

        await edit(first, 2)
        await first.get_by_role("combobox").select_option("elevation")
        await expect(first.get_by_text("Viewer draft saved.", exact=True)).to_be_visible()
        initial = await snapshot()
        assert initial["state"] == {"pointSize": 2.0, "colorMode": "elevation"}
        await first.reload()
        await expect(slider).to_have_value("2")
        await expect(first.get_by_role("combobox")).to_have_value("elevation")

        lost_ack_commands = []

        async def lose_first_ack(route):
            if route.request.method != "PUT":
                return await route.continue_()
            lost_ack_commands.append(route.request.post_data_json)
            if len(lost_ack_commands) == 1:
                response = await route.fetch()
                assert response.status == 200
                return await route.abort()
            await route.continue_()

        await first.route("**/api/pointcloud/pc_e2e/draft", lose_first_ack)
        await edit(first, 3)
        await expect(first.get_by_role("button", name="Retry draft")).to_be_visible()
        await first.get_by_role("button", name="Retry draft").click()
        await expect(first.get_by_text("Viewer draft saved.", exact=True)).to_be_visible()
        assert len(lost_ack_commands) == 2 and lost_ack_commands[0] == lost_ack_commands[1]
        after_retry = await snapshot()
        assert after_retry["revision"] == initial["revision"] + 1
        await first.unroute("**/api/pointcloud/pc_e2e/draft", lose_first_ack)

        second = await context.new_page()
        await second.goto(f"{base}/viewer/pc_e2e")
        await expect(second.get_by_role("slider")).to_have_value("3")
        await edit(first, 4)
        await expect(first.get_by_text("Viewer draft saved.", exact=True)).to_be_visible()
        winner = await snapshot()
        await edit(second, 2.5)
        await expect(second.get_by_role("button", name="Load latest saved draft")).to_be_visible()
        await expect(second.get_by_role("slider")).to_have_value("2.5")
        current = await snapshot()
        assert current == winner
        assert current["state"] == {"pointSize": 4.0, "colorMode": "elevation"}, current
        await second.get_by_role("button", name="Load latest saved draft").click()
        await expect(second.get_by_role("slider")).to_have_value("4")
        result = {
            "restore_after_reload": "pass", "lost_ack_exact_retry": "pass",
            "two_tabs_stale_save": "pass", "local_conflict_edits_preserved": "pass",
            "explicit_load_latest": "pass", "final_server_draft": current,
            "browser": browser.version,
            "scope": "real built Vue/HTTP/SQLite; Potree assets and 3D rendering excluded",
        }
        await browser.close()
        return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = asyncio.run(run(args.base_url))
    text = json.dumps(result, indent=2)
    print(text)
    if args.output:
        args.output.write_text(text + "\n")
