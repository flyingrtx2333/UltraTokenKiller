"""Freeze upstream evidence, never import upstream implementations into UTK."""
import hashlib
import json
import re
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
BASELINES = {
    "headroom": ("chopratejas/headroom", "bc21c9370793f7e4aa94ac4c5d9a67a8d2dd0df9"),
    "rtk": ("rtk-ai/rtk", "0924356b4caba4989607227b7c8824d3d8098719"),
    "caveman": ("JuliusBrussee/caveman", "542442bab314973709f95b85b1ac0b3f6f5b5dc6"),
}


def main():
    evidence = {}
    capabilities = []
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        for name, (repo, sha) in BASELINES.items():
            response = client.get(f"https://api.github.com/repos/{repo}/git/trees/{sha}?recursive=1")
            response.raise_for_status()
            tree = response.json()
            if tree.get("truncated"):
                raise RuntimeError("Incomplete tree; do not freeze a truncated inventory")
            paths = [item["path"] for item in tree["tree"] if item["type"] == "blob"]
            source_paths = ["README.md"]
            if name == "rtk":
                source_paths += ["src/main.rs"]
                source_paths += [p for p in paths if p.startswith("src/cmds/") and p.endswith(".rs")]
            if name == "caveman":
                source_paths += ["skills/caveman/SKILL.md"]
            sources = []
            for path in source_paths:
                url = f"https://raw.githubusercontent.com/{repo}/{sha}/{path}"
                response = client.get(url)
                response.raise_for_status()
                content = response.text
                record = {"path": path, "url": f"https://github.com/{repo}/blob/{sha}/{path}",
                          "sha256": hashlib.sha256(response.content).hexdigest()}
                if name == "rtk" and path.endswith(".rs"):
                    # Freeze all clap enum variants, including nested subcommands and aliases.
                    lines = content.splitlines()
                    enums = []
                    active = None
                    depth = 0
                    for number, line in enumerate(lines, 1):
                        match = re.search(r"(?:pub\s+)?enum\s+(\w+)", line)
                        if match and ("Command" in match[1] or match[1] == "Commands"):
                            active = match[1]
                            depth = 0
                        if active:
                            if depth == 1:
                                variant = re.match(r"^    ([A-Z]\w*)\s*(?:\{|\(|,|$)", line)
                                if variant:
                                    enums.append({"enum": active, "variant": variant[1], "line": number})
                            depth += line.count("{") - line.count("}")
                            if depth == 0:
                                active = None
                    record["command_variants"] = enums
                    for entry in enums:
                        identifier = f"tools.{entry['enum']}.{entry['variant']}"
                        capabilities.append({"id": identifier, "upstream": "rtk", "source": record["url"]+f"#L{entry['line']}",
                                             "input": entry["variant"], "behavior": "Match the frozen command's documented output and execution contract",
                                             "exceptions": ["unknown output version", "binary/machine output", "interactive execution"],
                                             "status": "unverified", "tests": [], "scope": "requires_review"})
                if path == "README.md":
                    record["documented_commands"] = [{"line": i, "command": line.strip().split(" #", 1)[0]}
                                                     for i, line in enumerate(content.splitlines(), 1)
                                                     if line.strip().startswith("rtk ")]
                sources.append(record)
            evidence[name] = {"repository": repo, "commit": sha, "sources": sources,
                              "test_paths": [p for p in paths if "test" in p.lower() or "fixture" in p.lower()]}
    target = ROOT / "src/ultratokenkiller/data"
    target.mkdir(parents=True, exist_ok=True)
    (target / "upstream-lock.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    # This is a discovery inventory, not a claim that enum extraction is a reviewed parity spec.
    (target / "command-inventory.json").write_text(json.dumps(capabilities, indent=2), encoding="utf-8")
    print(f"Frozen {len(evidence)} repositories, {len(capabilities)} command variants")


if __name__ == "__main__":
    main()
