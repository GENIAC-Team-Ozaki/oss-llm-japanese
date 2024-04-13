import json
from argparse import ArgumentParser
import logging
import pathlib


def load_jsonl(file_path):
    data = []
    with open(file_path, "r") as file:
        for line in file:
            data.append(json.loads(line))
    return data


def save_jsonl(data, file_path):
    with open(
        file_path, "w", encoding="utf-8"
    ) as file:  # ファイルをUTF-8エンコーディングで開く
        for item in data:
            file.write(json.dumps(item, ensure_ascii=False) + "\n")


def main() -> None:
    logger = logging.getLogger(__name__)
    parser = ArgumentParser()
    parser.add_argument(
        "--input_dir",
        type=str,
        help="Path to the data directory.",
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        help="Path to the output directory.",
    )
    parser.add_argument(
        "--output_file_name",
        type=str,
        default="combined_train.jsonl",
        help="Name of the output file which combines all input files. Default is 'combined_train.jsonl'."
    )

    args = parser.parse_args()

    input_dir: pathlib.Path = pathlib.Path(args.input_dir)
    output_dir: pathlib.Path = pathlib.Path(args.output_dir)
    output_file_name: str = str(args.output_file_name)
    output_dir.mkdir(parents=True, exist_ok=True)
    files_content = []

    while True:
        file_name = input(f"結合したいjsonlファイルの、input_dirディレクトリ内のファイル名を入力してください（例：CC_train_10000.jsonl）（完了する場合は'end'）: ")
        if file_name == "end":
            break
        full_path = input_dir / file_name
        if not full_path.exists():
            logger.error(f"File {str(full_path)}が見つかりません。再度入力してください。")
            continue
        file_content = load_jsonl(full_path)
        files_content.extend(file_content)
        logger.info(f"File {full_path}が追加されました。")

    output_full_path = output_dir / output_file_name
    save_jsonl(files_content, output_full_path)
    # with open(output_full_path, 'w') as output_file:
    #     for content in files_content:
    #         output_file.write(json.dumps(content) + '\n')

    logger.info(f"入力されたファイルを結合したjsonlの内容が {output_full_path} に保存されました。")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(name)s:%(lineno)d: %(levelname)s: %(message)s",
    )
    main()
