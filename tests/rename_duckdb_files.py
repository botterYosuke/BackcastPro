import os
import glob
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

TARGET_DIR = r"S:\jp\stocks_minute"
PATTERN = "stocks_minute_*.duckdb"

def rename_files():
    files = glob.glob(os.path.join(TARGET_DIR, PATTERN))
    logger.info(f"Found {len(files)} files to process.")

    renamed_count = 0
    skipped_count = 0
    conflict_count = 0

    for old_path in files:
        filename = os.path.basename(old_path)
        # stocks_minute_13010.duckdb -> 13010
        code = filename.replace("stocks_minute_", "").replace(".duckdb", "")
        # 13010 -> 1301
        truncated_code = code[:4]
        new_filename = f"{truncated_code}.duckdb"
        new_path = os.path.join(TARGET_DIR, new_filename)

        if os.path.exists(new_path):
            if old_path == new_path:
                logger.debug(f"Skipping {filename} (already named correctly)")
                skipped_count += 1
                continue
            logger.warning(f"Conflict: {new_filename} already exists. Skipping {filename}")
            conflict_count += 1
            continue

        try:
            os.rename(old_path, new_path)
            logger.info(f"Renamed: {filename} -> {new_filename}")
            renamed_count += 1
        except Exception as e:
            logger.error(f"Error renaming {filename}: {e}")

    logger.info(f"Summary: Renamed {renamed_count}, Skipped {skipped_count}, Conflicts {conflict_count}")

if __name__ == "__main__":
    rename_files()
