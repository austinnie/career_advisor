"""命令行工具：从 O*NET 目录构建职业快照。
用法：python -m career_advisor.data.build_snapshot --onet-dir E:\\onet\\db_30_1
"""
import argparse, sys
from pathlib import Path
from .seed_loader import build_snapshot


def main():
    parser = argparse.ArgumentParser(description="构建职业库快照")
    parser.add_argument("--onet-dir", required=True,
                        help="O*NET 数据库 txt 文件所在目录")
    parser.add_argument("--output", default=None,
                        help="输出 JSON 路径（默认到 data/snapshots/occupations.json）")
    parser.add_argument("--min-skills", type=int, default=3,
                        help="职业至少包含的技能条数（默认 3）")
    args = parser.parse_args()
    try:
        stats = build_snapshot(args.onet_dir,
                               Path(args.output) if args.output else None,
                               args.min_skills)
    except FileNotFoundError as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"[成功] 解析 {stats['parsed']} 条，保留 {stats['kept']} 条 → {stats['path']}")


if __name__ == "__main__":
    main()