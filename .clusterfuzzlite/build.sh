#!/bin/bash
# Build the Python atheris target into $OUT (APP-PARSE-001).
set -euo pipefail
cd "${SRC:-.}"
python3 -m pip install --require-hashes -r .clusterfuzzlite/requirements.txt
install -d "${OUT}"
install -m 0644 fuzz/fuzz_cache_segment.py "${OUT}/fuzz_cache_segment.py"
printf '%s\n' '#!/bin/bash' 'export PYTHONPATH="${SRC}/src"' 'exec python3 "${OUT}/fuzz_cache_segment.py"' > "${OUT}/fuzz_cache_segment"
chmod 0755 "${OUT}/fuzz_cache_segment"
