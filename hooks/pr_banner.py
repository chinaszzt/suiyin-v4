"""
mkdocs hook：在 Cloudflare Pages PR preview build 时，
从 GitHub API 拿当前 PR 信息（编号 + 改动文件清单），塞进 config.extra.pr_info。

theme override (overrides/main.html) 读这个数据，在 banner 里渲染：
  - 改动文件清单（带链接跳本站对应页）
  - 改动文件页面顶部「⇆ 并排对比 main」按钮（指向 /_compare/?page=...）

main build / 本地 build / 找不到 PR 时静默跳过，banner 不显示。
"""

import json
import os
import urllib.error
import urllib.request

GITHUB_REPO = "chinaszzt/suiyin-v4"
MAIN_URL = "https://suiyin-v4.pages.dev"


def _gh_get(path: str):
    """GET https://api.github.com/<path>, 返回解析后的 JSON，失败返回 None。

    优先用 GITHUB_TOKEN / GH_TOKEN 认证（unauthenticated 限流 60 次/小时，太脆弱）。
    """
    url = f"https://api.github.com/{path}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "suiyin-v4-mkdocs-hook",
    }
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.load(r)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        print(f"[pr_banner] GitHub API {path} failed: {e}")
        return None


def on_config(config, **kwargs):
    branch = os.getenv("CF_PAGES_BRANCH", "")
    sha = os.getenv("CF_PAGES_COMMIT_SHA", "")

    # main / local build：跳过
    if not branch or branch == "main" or not sha:
        return config

    # 反查 PR 编号
    pulls = _gh_get(f"repos/{GITHUB_REPO}/commits/{sha}/pulls")
    if not pulls:
        print(f"[pr_banner] No PR found for sha {sha}, skipping.")
        return config

    pr = pulls[0]
    pr_number = pr["number"]
    pr_title = pr["title"]
    pr_html_url = pr["html_url"]

    # 拿改动文件清单（只关心 docs/sdd/**/*.md）
    files = _gh_get(f"repos/{GITHUB_REPO}/pulls/{pr_number}/files?per_page=100")
    if files is None:
        return config

    changed_paths = []
    for f in files:
        filename = f["filename"]
        if not filename.startswith("docs/sdd/"):
            continue
        if not filename.endswith(".md"):
            continue
        # docs/sdd/methodology.md → methodology
        # docs/sdd/adrs/0001-foo.md → adrs/0001-foo
        rel = filename[len("docs/sdd/"):]
        rel = rel[:-len(".md")]
        changed_paths.append(rel)

    config["extra"]["pr_info"] = {
        "number": pr_number,
        "title": pr_title,
        "pr_url": pr_html_url,
        "main_url": MAIN_URL,
        "changed_paths": changed_paths,
    }
    print(
        f"[pr_banner] PR #{pr_number}: {len(changed_paths)} doc files changed "
        f"({', '.join(changed_paths) if changed_paths else 'none'})"
    )
    return config
