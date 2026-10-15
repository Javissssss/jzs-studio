"""Stand-in for `codex exec` in tests: echo a canned draft into the -o file,
and when the prompt asks for art, write figures.json + slot_XX.html in -C dir."""
import json, os, re, sys

args = sys.argv[1:]
prompt = sys.stdin.read()
out = args[args.index("-o") + 1]
cwd = args[args.index("-C") + 1]
print("fake codex: thinking")
if "slot_<序号>.html" in prompt:
    for n in re.findall(r"序号 (\d+)", prompt):
        with open(os.path.join(cwd, f"slot_{n}.html"), "w", encoding="utf-8") as f:
            f.write('<div id="figure" style="width:1080px;height:608px;background:#eef">art</div>')
    with open(os.path.join(cwd, "figures.json"), "w", encoding="utf-8") as f:
        json.dump([], f)
    text = "DONE"
else:
    text = os.environ.get("FAKE_CODEX_TEXT", "")
with open(out, "w", encoding="utf-8") as f:
    f.write(text)
sys.exit(int(os.environ.get("FAKE_CODEX_RC", "0")))
