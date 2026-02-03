#run_test_suite.sh

#!/usr/bin/env bash
if [ -z "${BASH_VERSION:-}" ]; then
  exec /usr/bin/env bash "$0" "$@"
fi

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $1"; }

PG_PREFIX="/usr/local/pgsql"
PG_CONFIG="${PG_PREFIX}/bin/pg_config"
PG_REGRESS="${PG_PREFIX}/lib/pgxs/src/test/regress/pg_regress"
PG_BINDIR="${PG_PREFIX}/bin"

TEMP_PORT="${TEMP_PORT:-65432}"
ENCODING="${ENCODING:-UTF8}"
GCOV_STRIP="${GCOV_PREFIX_STRIP:-2}"

###############################################################################
# Checks
###############################################################################
check_root() {
  if [ "${EUID}" -ne 0 ]; then
    log_error "此脚本需要 root 权限运行"
    exit 1
  fi
}

check_test_suite_path() {
  local suite="$1"
  [ -n "$suite" ] || { log_error "请提供测试套件路径"; exit 1; }
  [ -d "$suite" ] || { log_error "测试套件路径不存在: $suite"; exit 1; }
  [ -f "$suite/Makefile" ] || { log_error "测试套件路径中没有 Makefile: $suite"; exit 1; }
}

check_postgresql_paths() {
  [ -f "${PG_PREFIX}/bin/pg_ctl" ] || { log_error "未找到 pg_ctl"; exit 1; }
  [ -f "${PG_CONFIG}" ]           || { log_error "未找到 pg_config"; exit 1; }
  [ -x "${PG_REGRESS}" ]          || { log_error "未找到 pg_regress"; exit 1; }
}

check_postgres_user() {
  id "postgres" &>/dev/null || { log_error "postgres 用户不存在"; exit 1; }
}

infer_target_from_suite() {
  local suite="$1"
  local my_dir
  my_dir="$(basename "$(dirname "$suite")")"
  [[ "$my_dir" =~ ^my_ ]] || { log_error "父目录不是 my_*：$my_dir"; exit 1; }

  local cfile="${my_dir#my_}"
  [ -n "$cfile" ] || { log_error "推导 C 文件名失败：$my_dir"; exit 1; }

  local c_dir
  c_dir="$(dirname "$(dirname "$suite")")"
  local c_path="${c_dir}/${cfile}.c"
  echo "$cfile|$c_path|$c_dir|$my_dir"
}


infer_regress_tests() {
  local suite="$1"
  local mk="${suite}/Makefile"
  local tests=""
  tests="$(awk '
    BEGIN{found=0}
    /^[[:space:]]*#/ {next}
    /^[[:space:]]*REGRESS[[:space:]]*=/ && !found {
      found=1
      sub(/^[[:space:]]*REGRESS[[:space:]]*=[[:space:]]*/, "", $0)
      sub(/[[:space:]]*#.*/, "", $0)
      gsub(/[[:space:]]+/, " ", $0)
      print $0
      exit
    }' "$mk" || true)"
  if [ -n "${tests}" ]; then
    echo "${tests}"
    return 0
  fi

  local base
  base="$(basename "$suite")"
  if [[ "$base" =~ ^test_(.+)_suite$ ]]; then
    echo "test_${BASH_REMATCH[1]}"
    return 0
  fi

  log_error "无法推导回归测试名"
  exit 1
}


root_build_and_install_extension() {
  local suite="$1"
  log_info "=== Root 阶段：build + install extension（PGXS）==="
  cd "$suite"

  local error_file="${suite}/test_errors.txt"
  # 初始运行前清理旧的错误文件
  rm -f "$error_file"

  make clean >/dev/null 2>&1 || true
  if grep -qE '^[[:space:]]*extra_clean:' Makefile 2>/dev/null; then
    make extra_clean >/dev/null 2>&1 || true
  fi

  hard_clean_suite_artifacts "$suite"
  
  # 确保 log 目录在编译前就存在
  mkdir -p "${suite}/log" "${suite}/gcov_out"

  log_info "make (extension)..."
  if ! make PG_CONFIG="$PG_CONFIG" > "${suite}/log/make.log" 2>&1; then
    log_error "编译失败，错误已记录至 test_errors.txt"
    echo "--- Compilation Error (make) ---" > "$error_file"
    cat "${suite}/log/make.log" >> "$error_file"
    chmod 666 "$error_file"
    return 1
  fi

  log_info "make install (extension)..."
  if ! make PG_CONFIG="$PG_CONFIG" install > "${suite}/log/make_install.log" 2>&1; then
    log_error "安装失败，错误已记录至 test_errors.txt"
    echo "--- Installation Error (make install) ---" > "$error_file"
    cat "${suite}/log/make_install.log" >> "$error_file"
    chmod 666 "$error_file"
    return 1
  fi

  chown -R postgres:postgres "$suite"
  chmod -R u+rwX,g+rwX,o+rX "$suite" || true

  log_success "Root 阶段完成：extension 已 install"
}

hard_clean_suite_artifacts() {
  local suite="$1"
  cd "$suite"
  rm -rf tmp_check tmp_check_iso results regression.diffs regression.out output_iso log 2>/dev/null || true
  rm -f ./*.gcda ./*.gcno ./*.gcov ./*.c.gcov 2>/dev/null || true
  rm -rf ./gcov_out 2>/dev/null || true
}

postgres_run_pg_regress_with_gcov() {
  local suite="$1"
  local tests="$2"
  log_info "=== Postgres 阶段：pg_regress（显式 GCOV_PREFIX）==="
  
  local error_file="${suite}/test_errors.txt"

  runuser -u postgres -- bash -lc "
    set -euo pipefail
    cd '$suite'
    rm -rf tmp_check tmp_check_iso results regression.diffs regression.out output_iso 2>/dev/null || true
    mkdir -p gcov_out log
    export GCOV_PREFIX=\"\$PWD/gcov_out\"
    export GCOV_PREFIX_STRIP='${GCOV_STRIP}'

    rc=0
    '${PG_REGRESS}' \
      --inputdir=./ \
      --bindir='${PG_BINDIR}' \
      --temp-instance=./tmp_check \
      --port='${TEMP_PORT}' \
      --encoding='${ENCODING}' \
      --no-locale \
      ${tests} > log/pg_regress.run.log 2>&1 || rc=\$?

    echo \$rc > log/pg_regress.rc

    # 关键：无论 rc 是多少，都不把它向外抛出
    exit 0
  "

  # 下面：你可以选择是否记录 diffs，但不要让它触发失败/下一轮
  if [ -f "${suite}/regression.diffs" ]; then
    log_warning "pg_regress 产生 diffs（已忽略回归失败，用于诊断）：${suite}/regression.diffs"
    cp -f "${suite}/regression.diffs" "${suite}/log/pg_regress.diffs.txt" || true
    chmod 666 "${suite}/log/pg_regress.diffs.txt" 2>/dev/null || true
  else
    log_info "pg_regress 未产生 diffs（或未输出 diffs 文件）"
  fi

  log_success "pg_regress 完成（日志：${suite}/log/pg_regress.run.log；rc：${suite}/log/pg_regress.rc）"
}

find_gcda_path_by_basename() {
  local suite="$1"
  local base="$2"  # without suffix
  find "${suite}/gcov_out" -type f -name "${base}.gcda" | head -n 1 || true
}

find_gcda_any() {
  local suite="$1"
  find "${suite}/gcov_out" -type f -name "*.gcda" | head -n 10 || true
}

# ---------- static include detection (suite-local wrapper TU) ----------
detect_wrapper_translation_unit() {
  local suite="$1"
  local target_cfile="$2"  # e.g., ascii
  grep -RslE "^[[:space:]]*#include[[:space:]]+\"\\.\\./\\.\\./${target_cfile}\\.c\"" \
    "$suite" --include='*.c' | head -n 1 || true
}

# ---------- template include detection (e.g., levenshtein.c included by varlena.c) ----------
infer_includer_from_target_source() {
  local target_c_path="$1"

  # Match: "This file is included by varlena.c twice"
  local inc
  inc="$(grep -Eo 'included by[[:space:]]+[A-Za-z0-9_]+\.c' "$target_c_path" \
        | head -n 1 \
        | awk '{print $3}' \
        | sed 's/\.c$//')" || true

  if [ -n "${inc:-}" ]; then
    echo "$inc"
    return 0
  fi

  echo ""
}

find_source_c_path_by_basename() {
  local root_dir="$1"
  local base="$2"
  local p="${root_dir}/${base}.c"
  if [ -f "$p" ]; then
    echo "$p"
    return 0
  fi
  find "$root_dir" -maxdepth 2 -type f -name "${base}.c" | head -n 1 || true
}

# ---------- Mode A: normal (non-static, directly compiled TU) ----------
sync_gcno_into_gcda_dir_from_src_tree() {
  local c_path="$1"
  local gcda_dir="$2"
  local src_gcno="${c_path%.c}.gcno"
  [ -f "$src_gcno" ] || { log_error "未找到源码树 gcno：$src_gcno"; exit 1; }
  log_info "复制 notes：$src_gcno -> $gcda_dir/"
  cp -f "$src_gcno" "$gcda_dir/"
}

generate_true_c_gcov_from_src_dir() {
  local suite="$1"
  local cfile="$2"
  local c_dir="$3"
  local gcda_dir="$4"

  log_info "修复权限：确保 postgres 可在源码目录写入 *.gcov"
  chown -R postgres:postgres "$c_dir" || true
  chmod -R u+rwX,g+rwX,o+rX "$c_dir" || true
  rm -f "$c_dir"/*.gcov "$c_dir"/*.c.gcov 2>/dev/null || true

  log_info "在源码目录运行 gcov：cd ${c_dir} && gcov -b -c -o ${gcda_dir} ${cfile}.c"
  runuser -u postgres -- bash -lc "
    set -euo pipefail
    cd '$c_dir'
    gcov -b -c -o '$gcda_dir' '${cfile}.c' >/dev/null
  "

  local produced="${c_dir}/${cfile}.c.gcov"
  [ -f "$produced" ] || { log_error "gcov 未生成预期文件：$produced"; exit 1; }

  local lines
  lines="$(wc -l < "$produced" | tr -d ' ')"
  [ "${lines}" -ge 10 ] || { log_error "生成的 ${produced} 行数过少（${lines}）"; exit 1; }

  cp -f "$produced" "${suite}/"
  log_success "已生成：${suite}/${cfile}.c.gcov"
}

# ---------- Mode B: suite-local static include (wrapper TU) ----------
generate_included_c_gcov_from_suite_dir() {
  local suite="$1"
  local target_cfile="$2"  # e.g., ascii -> want ascii.c.gcov
  local wrap_c="$3"        # e.g., /.../ascii_uut_wrap.c
  local wrap_base
  wrap_base="$(basename "$wrap_c" .c)"

  local wrap_gcda
  wrap_gcda="$(find_gcda_path_by_basename "$suite" "$wrap_base")"
  [ -n "$wrap_gcda" ] || { log_error "未找到 wrapper 的 gcda：${wrap_base}.gcda"; exit 1; }

  local wrap_gcno="${suite}/${wrap_base}.gcno"
  [ -f "$wrap_gcno" ] || { log_error "未找到 suite 编译产物 gcno：$wrap_gcno"; exit 1; }

  log_info "static-include 模式：wrapper=${wrap_base}"
  log_info "  data:  $wrap_gcda"
  log_info "  notes: $wrap_gcno"

  chown -R postgres:postgres "$suite" || true
  chmod -R u+rwX,g+rwX,o+rX "$suite" || true

  rm -f "$suite"/*.gcov "$suite"/*.c.gcov 2>/dev/null || true

  cp -f "$wrap_gcda" "${suite}/${wrap_base}.gcda"

  log_info "在 suite 编译目录运行 gcov：cd ${suite} && gcov -b -c -o . ${wrap_base}.c"
  runuser -u postgres -- bash -lc "
    set -euo pipefail
    cd '$suite'
    gcov -b -c -o . '${wrap_base}.c' >/dev/null
  "

  local produced="${suite}/${target_cfile}.c.gcov"
  [ -f "$produced" ] || {
    log_error "gcov 未生成目标覆盖文件：$produced"
    log_error "提示：请确认 ${wrap_base}.c 中确实 include 了 ../../${target_cfile}.c"
    exit 1
  }

  local lines
  lines="$(wc -l < "$produced" | tr -d ' ')"
  [ "${lines}" -ge 10 ] || { log_error "生成的 ${produced} 行数过少（${lines}）"; exit 1; }

  log_success "已生成（static-include）：${suite}/${target_cfile}.c.gcov"
}

# ---------- Mode C: template include by backend TU (e.g., levenshtein.c via varlena.c) ----------
generate_target_c_gcov_via_includer() {
  local suite="$1"
  local target_cfile="$2"     # e.g., levenshtein
  local c_dir="$3"            # e.g., .../src/backend/utils/adt
  local includer_base="$4"    # e.g., varlena
  local gcda_dir="$5"         # where includer.gcda lives

  local includer_path
  includer_path="$(find_source_c_path_by_basename "$c_dir" "$includer_base")"
  [ -n "$includer_path" ] || { log_error "未找到 includer 源码：${includer_base}.c（在 $c_dir 下）"; exit 1; }

  log_info "模板 include 覆盖模式：target=${target_cfile}.c 由 includer=${includer_base}.c 编译生成"

  chown -R postgres:postgres "$c_dir" || true
  chmod -R u+rwX,g+rwX,o+rX "$c_dir" || true
  rm -f "$c_dir"/*.gcov "$c_dir"/*.c.gcov 2>/dev/null || true

  local includer_gcno="${includer_path%.c}.gcno"
  [ -f "$includer_gcno" ] || { log_error "未找到 includer 的 gcno（源码树）：$includer_gcno"; exit 1; }

  log_info "复制 includer gcno：$includer_gcno -> $gcda_dir/"
  cp -f "$includer_gcno" "$gcda_dir/"

  log_info "在源码目录运行 gcov：cd ${c_dir} && gcov -b -c -o ${gcda_dir} ${includer_base}.c"
  runuser -u postgres -- bash -lc "
    set -euo pipefail
    cd '$c_dir'
    gcov -b -c -o '$gcda_dir' '${includer_base}.c' >/dev/null
  "

  local produced="${c_dir}/${target_cfile}.c.gcov"
  [ -f "$produced" ] || {
    log_error "gcov 未生成目标覆盖文件：$produced"
    log_error "诊断提示：请检查 ${target_cfile}.c 是否确实被 ${includer_base}.c include"
    exit 1
  }

  local lines
  lines="$(wc -l < "$produced" | tr -d ' ')"
  [ "${lines}" -ge 10 ] || { log_error "生成的 ${produced} 行数过少（${lines}）"; exit 1; }

  cp -f "$produced" "${suite}/"
  log_success "已生成（template-include）：${suite}/${target_cfile}.c.gcov"
}

###############################################################################
# Success criterion: two required *.c.gcov files exist in suite dir
###############################################################################
have_two_required_gcov() {
  local suite="$1"
  local base="$2"   # e.g., uuid (target source TU base)
  local ext="$3"    # e.g., test_uuid_in (extension TU base)

  [ -f "${suite}/${base}.c.gcov" ] && [ -f "${suite}/${ext}.c.gcov" ]
}

exit_if_success() {
  local suite="$1"
  local base="$2"
  local ext="$3"

  if have_two_required_gcov "$suite" "$base" "$ext"; then
    log_success "判定成功：已生成两个覆盖文件：${base}.c.gcov 与 ${ext}.c.gcov（不进入下一轮优化）"
    exit 0
  fi
}

###############################################################################
# main
###############################################################################
main() {
  local suite="${1:-}"
  suite="$(readlink -f "$suite")"

  check_root
  check_test_suite_path "$suite"
  check_postgresql_paths
  check_postgres_user

  local run_log_file="${suite}/run_test.txt"
  : > "$run_log_file"
  exec > >(tee -a "$run_log_file") 2>&1
  log_info "终端输出将同时写入: ${run_log_file}（覆盖写入）"

  local inferred cfile c_path c_dir my_dir
  inferred="$(infer_target_from_suite "$suite")"
  cfile="$(echo "$inferred" | cut -d'|' -f1)"
  c_path="$(echo "$inferred" | cut -d'|' -f2)"
  c_dir="$(echo "$inferred" | cut -d'|' -f3)"
  my_dir="$(echo "$inferred" | cut -d'|' -f4)"

  log_info "推导信息：suite=$suite, target=${cfile}.c, source_dir=$c_dir"
  [ -f "$c_path" ] || { log_error "未找到待测源码文件：$c_path"; exit 1; }

  local tests
  tests="$(infer_regress_tests "$suite")"
  log_info "回归测试项：${tests}"

  root_build_and_install_extension "$suite"
  postgres_run_pg_regress_with_gcov "$suite" "$tests"

  # --- Mode B: suite-local static include wrapper (highest priority) ---
  local wrap_c
  wrap_c="$(detect_wrapper_translation_unit "$suite" "$cfile")"
  if [ -n "$wrap_c" ]; then
    log_info "检测到 static-include wrapper：$wrap_c（使用 static-include 覆盖模式）"
    generate_included_c_gcov_from_suite_dir "$suite" "$cfile" "$wrap_c"
    log_success "脚本执行成功（static-include）：生成 ${suite}/${cfile}.c.gcov"
    # exit 0
  fi

  # --- Mode A: normal direct TU ---
  local gcda_path
  gcda_path="$(find_gcda_path_by_basename "$suite" "$cfile")"

  if [ -z "$gcda_path" ]; then
    log_warning "未找到 ${cfile}.gcda；尝试模板 include 覆盖模式（从源码注释推导 includer TU）"

    local any_gcda
    any_gcda="$(find "${suite}/gcov_out" -type f -name "*.gcda" | head -n 1 || true)"
    if [ -z "$any_gcda" ]; then
      log_error "gcov_out 下没有任何 .gcda：说明测试未触发后端执行，或后端未用 --coverage 构建，或 GCOV_PREFIX 未生效"
      log_error "请检查：ls -R ${suite}/gcov_out"
      exit 1
    fi

    local includer
    includer="$(infer_includer_from_target_source "$c_path")"
    if [ -z "$includer" ]; then
      log_error "无法从 ${c_path} 推导 includer（模板 include 编译单元）"
      log_error "gcov_out 下存在的 .gcda（前几项）："
      find_gcda_any "$suite" | sed 's/^/[GCDA] /' || true
      log_error "你可以手工确认：levenshtein.c 通常由 varlena.c include"
      exit 1
    fi

    log_info "推导到 includer：${includer}.c"
    gcda_path="$(find_gcda_path_by_basename "$suite" "$includer")"
    if [ -z "$gcda_path" ]; then
      log_error "未找到 includer 的 gcda：${includer}.gcda"
      log_error "gcov_out 下存在的 .gcda（前几项）："
      find_gcda_any "$suite" | sed 's/^/[GCDA] /' || true
      exit 1
    fi

    local gcda_dir
    gcda_dir="$(dirname "$gcda_path")"
    log_info "定位到 includer gcda：$gcda_path（dir=$gcda_dir）"

    generate_target_c_gcov_via_includer "$suite" "$cfile" "$c_dir" "$includer" "$gcda_dir"
    log_success "脚本执行成功（template-include）：生成 ${suite}/${cfile}.c.gcov"
    exit 0
  fi

  log_info "检测为普通模式（non-static）：定位到 gcda：$gcda_path"
  local gcda_dir
  gcda_dir="$(dirname "$gcda_path")"

  sync_gcno_into_gcda_dir_from_src_tree "$c_path" "$gcda_dir"
  generate_true_c_gcov_from_src_dir "$suite" "$cfile" "$c_dir" "$gcda_dir"

  log_success "脚本执行成功：生成 ${suite}/${cfile}.c.gcov"
  exit_if_success "$suite" "$cfile" "$tests"
  
    ###############################################################################
  # EXTRA: also generate extension TU gcov (test_uuid_in.c.gcov)
  ###############################################################################
  log_info "额外生成 extension 覆盖率：${tests}.c.gcov"

  ext_base="$tests"   # e.g., test_uuid_in

  ext_gcda="$(find "$suite/gcov_out" -type f -name "${ext_base}.gcda" | head -n 1 || true)"
  if [ -z "$ext_gcda" ]; then
    log_warning "未找到 ${ext_base}.gcda（extension TU），跳过 ${ext_base}.c.gcov 生成"
  else
    # 关键点：suite 编译目录里应当有 ${ext_base}.gcno
    if [ ! -f "$suite/${ext_base}.gcno" ]; then
      log_error "未找到 suite 目录中的 notes 文件：$suite/${ext_base}.gcno"
      log_error "说明 extension 可能未以 --coverage 编译，或编译产物不在 suite 根目录"
      exit 1
    fi

    log_info "定位到 extension gcda：$ext_gcda"
    log_info "将 gcda 拷回 suite 编译目录以匹配 gcno"
    rm -f "$suite/${ext_base}.gcda" "$suite/${ext_base}.c.gcov" 2>/dev/null || true
    cp -f "$ext_gcda" "$suite/${ext_base}.gcda"
    chown postgres:postgres "$suite/${ext_base}.gcda" 2>/dev/null || true
    chmod 666 "$suite/${ext_base}.gcda" 2>/dev/null || true

    log_info "在 suite 目录运行 gcov：cd $suite && gcov -b -c -o . ${ext_base}.c"
    runuser -u postgres -- bash -lc "
      set -euo pipefail
      cd '$suite'
      gcov -b -c -o . '${ext_base}.c' >/dev/null
    "

    if [ -f "$suite/${ext_base}.c.gcov" ]; then
      log_success "已生成：${suite}/${ext_base}.c.gcov"
    else
      log_warning "gcov 未生成 ${ext_base}.c.gcov（请检查 ${ext_base}.c 是否参与编译，或路径是否正确）"
    fi
  fi

  # Final success decision (two .c.gcov files)
  exit_if_success "$suite" "$cfile" "$tests"

  log_error "判定失败：未同时生成 ${cfile}.c.gcov 与 ${tests}.c.gcov"
  exit 1

}

main "$@"