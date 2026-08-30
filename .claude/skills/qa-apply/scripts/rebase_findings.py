"""findings の entry を現行 dataset 行へ揃える（再ベース）。

/qa-apply の適用前に実行し、dataset の変更で古くなった finding の entry を現行行に更新する。

- 通常動作: status が pending/approved で entry が現行行に無く、キー（名ファイル: 読み col0 /
  姓ファイル: 漢字 col0）一致の現行行が一意に存在するものは entry をその行に書き換える（id は不変）。
  同キー行が無い・複数ある場合は「未解決」として報告するだけで変更しない。
- --reopen-unapplied: status が applied かつ action=remove_kanji で、現行の同キー行（一意）に
  対象漢字（`,` / `、` 区切りで複数可）が1つでも残っているものは、entry を現行行に更新し
  status を approved に戻す。監査用に evidence 末尾へ「（再オープン: 未適用を検出 YYYY-MM-DD）」を追記する。

書き込みは tmp→os.replace（原子的）。--dry-run なら件数を表示するだけで書き込まない。
"""
import argparse
import datetime
import os
import sys
from typing import Dict, List

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.abspath(os.path.join(
    _HERE, os.pardir, os.pardir, "validate-dataset", "scripts")))

import findings_io  # noqa: E402
import triage_server  # noqa: E402

REBASABLE = ("pending", "approved")
REOPEN_NOTE = "（再オープン: 未適用を検出 %s）"


def rebase(findings, index, reopen_unapplied=False, today=None):
    # type: (List[dict], Dict[str, dict], bool, str) -> dict
    """findings をその場で更新し {"rebased": [id], "reopened": [id], "unresolved": [id]} を返す。"""
    today = today or datetime.date.today().isoformat()
    result = {"rebased": [], "reopened": [], "unresolved": []}  # type: Dict[str, List[str]]
    for d in findings:
        info = index.get(d["file"])
        if info is None:
            continue
        current = triage_server.current_row_for(d["entry"], info)
        status = d["status"]
        if status in REBASABLE:
            if d["entry"] in info["rows"]:
                continue
            if current is None:
                result["unresolved"].append(d["id"])
                continue
            d["entry"] = current
            result["rebased"].append(d["id"])
        elif reopen_unapplied and status == "applied" \
                and d["proposed_fix"]["action"] == "remove_kanji":
            if current is None:
                continue
            current_kanji = current.split(",")[2:]
            targets = triage_server.split_values(d["proposed_fix"].get("value", ""))
            if any(k in current_kanji for k in targets):
                d["entry"] = current
                d["status"] = "approved"
                d["evidence"] = (d.get("evidence") or "") + REOPEN_NOTE % today
                result["reopened"].append(d["id"])
    return result


def main():
    # type: () -> int
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--findings", required=True)
    parser.add_argument("--dataset-dir", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--reopen-unapplied", action="store_true",
                        help="applied の remove_kanji で漢字が残っているものを approved に戻す")
    args = parser.parse_args()
    findings = findings_io.load_findings(args.findings)
    index = triage_server.load_dataset_index(args.dataset_dir)
    result = rebase(findings, index, reopen_unapplied=args.reopen_unapplied)
    for i in result["reopened"]:
        print("再オープン（未適用の remove_kanji）: %s" % i)
    for i in result["unresolved"]:
        print("未解決（同キーの現行行が無いか複数）: %s" % i)
    mode = "（dry-run: 書き込みなし）" if args.dry_run else ""
    print("再ベース %d 件 / 再オープン %d 件 / 未解決 %d 件%s"
          % (len(result["rebased"]), len(result["reopened"]), len(result["unresolved"]), mode))
    if not args.dry_run and (result["rebased"] or result["reopened"]):
        triage_server.save_atomic(args.findings, findings)
        print("書き込み: %s" % args.findings)
    return 0


def _force_utf8_output():
    # type: () -> None
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure") and (stream.encoding or "").lower() not in ("utf-8", "utf8"):
            stream.reconfigure(encoding="utf-8", errors="replace")


if __name__ == "__main__":
    _force_utf8_output()
    sys.exit(main())
