set -euo pipefail

SH="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"  
ROOT="$(cd "$SH/.." && pwd)"                             
cd "$SH"

# Chon Python
PY="${PY:-}"
if [ -z "$PY" ]; then
  if [ -f ".venv/Scripts/python.exe" ]; then
    PY=".venv/Scripts/python.exe"
  elif [ -f ".venv/bin/python" ]; then
    PY=".venv/bin/python"
  else
    PY="python"
  fi
fi

IMAGE="${IMAGE:-hoangphuc858903/selfheal:dev}"

# ham tro giup 
need_env() {   # need_env TEN_BIEN
  if [ -z "${!1:-}" ]; then
    echo "LOI: chua dat bien moi truong $1 (vi du: export $1=...). Xem muc F1.6." >&2
    exit 1
  fi
}

need_cmd() {   # need_cmd TEN_LENH
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "LOI: khong tim thay lenh '$1'. Hay cai dat truoc (xem muc F1.1)." >&2
    exit 1
  fi
}

need_llm_key() {   # chi can khoa Groq khi LLM_BACKEND la groq 
  if [ "${LLM_BACKEND:-groq}" = "groq" ]; then
    need_env GROQ_API_KEY
  fi
}

need_real_run() {  # DRY_RUN=true 
  local dry="${DRY_RUN:-false}"
  if [ "${dry,,}" = "true" ]; then
    echo "LOI: DRY_RUN=true se khong thuc thi hanh dong nao, ket qua vo nghia. Chay 'unset DRY_RUN' roi thu lai." >&2
    exit 1
  fi
}

use_prom() {      
  export PROMETHEUS_URL="${PROMETHEUS_URL:-http://localhost:9090}"
}

# Sim 
cmd_setup() {
  if [ ! -d ".venv" ]; then
    if command -v py >/dev/null 2>&1; then
      py -3.11 -m venv .venv
    else
      need_cmd python3.11
      python3.11 -m venv .venv
    fi
  fi
  # dung python trong venv vua tao
  if [ -f ".venv/Scripts/python.exe" ]; then PY=".venv/Scripts/python.exe"; else PY=".venv/bin/python"; fi
  "$PY" -m pip install --upgrade pip
  "$PY" -m pip install torch==2.5.1 --index-url https://download.pytorch.org/whl/cpu
  "$PY" -m pip install -r requirements.txt
  find selfheal -type d -not -name __pycache__ -exec touch {}/__init__.py \;
  echo "Xong setup. Kiem tra bang: bash scripts/kltn.sh test"
}

cmd_test() {
  "$PY" -m pytest -q
}

cmd_sanity() {
  PYTHONPATH=. "$PY" scripts/sanity_sim.py
}

cmd_train() {      # 3 seed x (PPO thuan, BC+PPO); STEPS mac dinh 300000
  local steps="${STEPS:-300000}" s
  for s in 0 1 2; do
    "$PY" -m selfheal.agent.train_ppo --steps "$steps" --seed "$s" --tag "ppo_s$s"
    "$PY" -m selfheal.agent.train_ppo --bc --steps "$steps" --seed "$s" --tag "bc_s$s"
  done
  echo "Xong. Xem learning curve: tensorboard --logdir logs/tb"
}

cmd_promote() {    # promote ( bc_s0)
  local tag="${1:-bc_s0}"
  local src="models/$tag/best_model.zip"
  if [ ! -f "$src" ]; then
    echo "LOI: khong thay $src (da chay 'train' chua?)" >&2
    exit 1
  fi
  cp "$src" models/current.zip
  echo "Da promote $src -> models/current.zip"
}

cmd_ablation() {   #  huan luyen 2 model ablation
  "$PY" -m selfheal.agent.train_ppo --bc --no-llm --tag abl_nollm
  "$PY" -m selfheal.agent.train_ppo --bc --no-forecast --tag abl_nofc
}

cmd_sim_campaign() {   # 6 phuong phap va 3 ablation, REPS mac dinh 15
  local reps="${REPS:-15}" m
  for m in native hpa keda rule rl hybrid; do
    "$PY" -m selfheal.experiments.run_campaign --mode sim --method "$m" --reps "$reps"
  done
  "$PY" -m selfheal.experiments.run_campaign --mode sim --method rl --reps "$reps" \
    --model models/abl_nollm/best_model.zip --no-llm --tag _nollm
  "$PY" -m selfheal.experiments.run_campaign --mode sim --method rl --reps "$reps" \
    --model models/ppo_s0/best_model.zip --tag _nobc
  "$PY" -m selfheal.experiments.run_campaign --mode sim --method rl --reps "$reps" \
    --model models/abl_nofc/best_model.zip --no-forecast --tag _nofc
}

cmd_analyze() {
  "$PY" -m selfheal.experiments.analyze
  "$PY" -m selfheal.experiments.plots
}

cmd_sim_all() {    
  cmd_test
  cmd_train
  cmd_promote bc_s0
  cmd_ablation
  cmd_sim_campaign
  cmd_analyze
}

#  cum kind va port-forward 
cmd_local_up() {
  need_cmd docker
  need_cmd kind
  need_cmd kubectl
  need_cmd helm
  bash "$ROOT/kubernetes/local/setup-local.sh"
}

cmd_pf_stop() {
  if [ -f .pf.pids ]; then
    local pid
    while read -r pid; do
      [ -n "$pid" ] && kill "$pid" 2>/dev/null || true
    done < .pf.pids
    rm -f .pf.pids
    echo "Da dung port-forward."
  else
    echo "Khong co .pf.pids (khong co port-forward nao do script khoi dong)."
  fi
}

cmd_pf() {
  need_cmd kubectl
  need_cmd curl
  cmd_pf_stop >/dev/null
  mkdir -p logs
  kubectl -n monitoring port-forward svc/prometheus-kube-prometheus-prometheus 9090:9090 > logs/pf_prometheus.log 2>&1 &
  echo $! > .pf.pids
  kubectl -n loadtest port-forward svc/locust-master 8089:8089 > logs/pf_locust.log 2>&1 &
  echo $! >> .pf.pids
  sleep 8
  curl -s -X POST -d "user_count=30&spawn_rate=5" http://localhost:8089/swarm \
    || echo "CANH BAO: chua bat duoc tai nen 30 user (xem logs/pf_locust.log)" >&2
  echo
  echo "Port-forward dang chay (PID trong .pf.pids): Prometheus http://localhost:9090 | Locust http://localhost:8089"
  echo "Dung bang: bash scripts/kltn.sh pf-stop"
}

# du lieu, hieu chinh, du bao 
cmd_collect() {    # thu du lieu offline, REPS mac dinh 6
  need_llm_key
  need_real_run
  use_prom
  mkdir -p logs
  "$PY" -m selfheal.experiments.collect_offline --reps "${REPS:-6}" 2>&1 \
    | tee "logs/collect_$(date +%Y%m%d_%H%M).log"
}

cmd_calibrate() {  # them --prom neu Prometheus con truy cap duoc, them --llm-eval neu da co file
  need_cmd curl
  use_prom
  if [ ! -f data/live/timeseries.csv ]; then
    echo "LOI: thieu data/live/timeseries.csv (chay 'collect' truoc)" >&2
    exit 1
  fi
  mkdir -p models
  local args=(--ts data/live/timeseries.csv --out models/sim_params.json)
  if [ -f data/llm_eval.csv ]; then
    args+=(--llm-eval data/llm_eval.csv)
  fi
  if curl -sf --max-time 3 "$PROMETHEUS_URL/-/ready" >/dev/null 2>&1; then
    args+=(--prom "$PROMETHEUS_URL")
  else
    echo "Luu y: khong ket noi duoc Prometheus -> bo qua --prom (startup_steps dung gia tri mac dinh)." >&2
  fi
  "$PY" -m selfheal.sim.calibrate "${args[@]}"
}

cmd_llm_eval() {   # llm-eval openai/gpt-oss-120b, ollama de chay cuc bo)
  local model="${1:-openai/gpt-oss-120b}"
  if [ "$model" = "ollama" ]; then
    "$PY" -m selfheal.llm.evaluate --rerun ollama --out data/llm_eval_ollama.csv
  else
    need_env GROQ_API_KEY
    local safe="${model//\//_}"
    "$PY" -m selfheal.llm.evaluate --rerun groq --model "$model" --out "data/llm_eval_${safe}.csv"
  fi
}

cmd_forecast() {   # forecast 
  local step="${1:-all}"
  use_prom
  case "$step" in
    all|export|train) ;;
    *) echo "LOI: forecast nhan all|export|train (nhan: '$step')" >&2; exit 1 ;;
  esac
  if [ "$step" = "all" ] || [ "$step" = "export" ]; then
    "$PY" -m selfheal.forecast.train_lstm export --prom "$PROMETHEUS_URL" --hours 16 --csv data/forecast.csv
  fi
  if [ "$step" = "all" ] || [ "$step" = "train" ]; then
    if [ ! -f data/forecast.csv ]; then
      echo "LOI: thieu data/forecast.csv (chay 'forecast export' khi cum con bat)" >&2
      exit 1
    fi
    "$PY" -m selfheal.forecast.train_lstm train --csv data/forecast.csv --epochs 30
  fi
}

cmd_finetune() {   # fine-tune online  ROUNDS, EPISODES de giam khi thieu thoi gian
  need_llm_key
  need_real_run
  use_prom
  if [ ! -f models/current.zip ]; then
    echo "LOI: thieu models/current.zip (chay 'train' + 'promote' truoc)" >&2
    exit 1
  fi
  "$PY" -m selfheal.agent.finetune --rounds "${ROUNDS:-3}" --episodes-per-round "${EPISODES:-12}"
}

# Live 
cmd_live_campaign() {   # live-campaign METHOD 
  local method="${1:-}" mode
  case "$method" in
    native) mode="native" ;;
    hpa)    mode="hpa" ;;
    keda)   mode="keda" ;;
    rule)   mode="native" ;;    
    hybrid) mode="native" ;;
    *) echo "LOI: METHOD phai la native|hpa|keda|rule|hybrid (nhan: '$method')" >&2; exit 1 ;;
  esac
  need_cmd kubectl
  need_real_run
  if [ "$method" = "hybrid" ]; then
    need_llm_key
  fi
  use_prom
  mkdir -p logs
  bash baselines/switch.sh "$mode"

  printf '\n' | "$PY" -m selfheal.experiments.run_campaign --mode live --method "$method" \
    --reps "${REPS:-5}" --scenarios 1,2,3,4,5,7 2>&1 | tee -a "logs/live_$method.log"
}

cmd_live_all() {
  local m
  for m in native hpa keda rule hybrid; do
    cmd_live_campaign "$m"
  done
}

# image, deploy, demo 
cmd_image() {
  need_cmd docker
  if [ ! -f models/current.zip ]; then
    echo "LOI: thieu models/current.zip (chay 'train' + 'promote' truoc)" >&2
    exit 1
  fi
  if [ ! -d models/forecaster ]; then
    echo "LOI: thieu models/forecaster (chay 'forecast' truoc)" >&2
    exit 1
  fi
  if [ "$(kubectl config current-context 2>/dev/null)" = "kind-selfheal" ] && \n     kubectl -n selfheal get deploy selfheal-controller >/dev/null 2>&1; then
    # build torch lam laptop/kind cham -> p99 vot -> controller dang chay se scale/chinh nham. Tam dung; deploy bat lai.
    echo "Tam dung selfheal-controller trong luc build (chay lai: bash scripts/kltn.sh deploy)"
    kubectl -n selfheal scale deploy selfheal-controller --replicas=0
  fi
  docker build -t "$IMAGE" "$SH"
  if command -v kind >/dev/null 2>&1; then
    local clusters
    clusters="$(kind get clusters 2>/dev/null || true)"
    if printf '%s\n' "$clusters" | grep -qx 'selfheal'; then
      kind load docker-image "$IMAGE" --name selfheal
    fi
  fi
  echo "Da build $IMAGE (tren EKS can docker push len registry, hoac dung image do CI build)."
}

cmd_deploy() {
  need_cmd kubectl
  need_env GROQ_API_KEY
  local ctx
  ctx="$(kubectl config current-context 2>/dev/null || true)"
  if [ "$IMAGE" = "hoangphuc858903/selfheal:dev" ] && [ "$ctx" != "kind-selfheal" ]; then
    echo "LOI: context '$ctx' khong phai cum kind. Tren EKS hay dat IMAGE=hoangphuc858903/selfheal:<git-sha> (image CI da push)." >&2
    exit 1
  fi
  kubectl apply -f k8s/rbac.yaml
  if [ "$ctx" = "kind-selfheal" ]; then   # rbac.yaml giu SLO cua EKS (200); kind do rieng o P-02 = 305
    kubectl -n selfheal patch configmap selfheal-config -p "{\"data\":{\"SLO_P99_MS\":\"${KIND_SLO_P99_MS:-305}\"}}"
  fi
  kubectl -n selfheal create secret generic selfheal-secrets \
    --from-literal=GROQ_API_KEY="$GROQ_API_KEY" \
    --from-literal=SLACK_WEBHOOK_URL="${SLACK_WEBHOOK_URL:-}" \
    --dry-run=client -o yaml | kubectl apply -f -
  # Thay image ngay trong manifest roi moi apply. Truoc day apply ':latest' roi 'set image' -> pod ':latest'
  # dang keo image (nang, co torch) khong xoa duoc, controller dung Recreate nen rollout ket "0 out of 1" (26/11 kind).
  sed "s#hoangphuc858903/selfheal:latest#${IMAGE}#g" k8s/controller.yaml | kubectl apply -f -

  kubectl -n selfheal scale deploy selfheal-controller --replicas=1
  kubectl -n selfheal rollout status deploy/selfheal-controller --timeout=300s
  kubectl -n selfheal rollout status deploy/selfheal-forecaster --timeout=300s
}

cmd_demo() {      
  local scenario="${SCENARIO:-3}" target="${TARGET:-}"
  case "$scenario" in
    1|2|3|4|5|6|7) ;;
    *) echo "LOI: SCENARIO phai la so tu 1 den 7 (nhan: '$scenario')" >&2; exit 1 ;;
  esac
  if [ -z "$target" ]; then
    if [ "$scenario" = "7" ]; then target="productcatalogservice"; else target="frontend"; fi
  fi
  need_cmd kubectl
  local ready
  ready="$(kubectl -n selfheal get deploy selfheal-controller -o jsonpath='{.status.readyReplicas}' 2>/dev/null || true)"
  if [ -z "$ready" ] || [ "$ready" = "0" ]; then
    echo "CANH BAO: selfheal-controller chua chay trong cum (bo qua neu dang chay controller tren laptop)." >&2
    echo "          Bat bang: bash baselines/switch.sh agent" >&2
  fi
  # Chi tiem khi cum on dinh (giong LiveEnv._wait_steady) + khong co su co dang mo, anomaly < nguong.
  # SKIP_STEADY=1 bo qua; STEADY_ONLY=1 chi kiem tra roi thoat (khong tiem); STEADY_TIMEOUT mac dinh 600 s.
  if [ "${SKIP_STEADY:-0}" != "1" ]; then
    use_prom
    local slo_p99 slo_err
    slo_p99="$(kubectl -n selfheal get configmap selfheal-config -o jsonpath='{.data.SLO_P99_MS}' 2>/dev/null || true)"
    slo_err="$(kubectl -n selfheal get configmap selfheal-config -o jsonpath='{.data.SLO_ERR}' 2>/dev/null || true)"
    if ! "$PY" -m selfheal.chaos.steady --slo-p99 "${slo_p99:-200}" --slo-err "${slo_err:-0.01}" \
        --timeout "${STEADY_TIMEOUT:-600}" --prom "$PROMETHEUS_URL"; then
      echo "LOI: cum chua on dinh (hoac khong doc duoc Prometheus) -> KHONG tiem. Thu lai sau, hoac SKIP_STEADY=1 de bo qua." >&2
      exit 1
    fi
  fi
  if [ "${STEADY_ONLY:-0}" = "1" ]; then
    echo "STEADY_ONLY=1: cum dang on dinh, khong tiem."
    return 0
  fi
  SCENARIO="$scenario" TARGET="$target" "$PY" -c "import os, uuid; from selfheal.chaos.injector import ChaosInjector; ChaosInjector(gt_path='data/demo/ground_truth.csv').inject(int(os.environ['SCENARIO']), os.environ['TARGET'], 'demo-' + uuid.uuid4().hex[:8], duration=120)"   # tach khoi data/ground_truth.csv (du lieu EKS)
  echo "Da tiem kich ban $scenario vao $target (120s). Theo doi:"
  echo "  Grafana : kubectl -n monitoring port-forward svc/prometheus-grafana 3000:80  ->  http://localhost:3000"
  echo "  Slack   : kenh dung SLACK_WEBHOOK_URL (RCA + hanh dong cua agent)"
  echo "  Log     : kubectl -n selfheal logs deploy/selfheal-controller -f"
  echo "  Don dep : bash scripts/kltn.sh clean   (bat buoc voi kich ban 2 va 6)"
}

cmd_clean() {
  "$PY" -c "from selfheal.chaos.injector import ChaosInjector; ChaosInjector().cleanup_all()"
}

#  EKS 
cmd_eks_up() {
  need_cmd terraform
  need_cmd aws
  need_cmd kubectl
  need_cmd helm
  bash "$ROOT/terraform-modules/eks-up.sh"
}

cmd_eks_down() {
  need_cmd terraform
  need_cmd kubectl
  need_cmd helm
  bash "$ROOT/terraform-modules/eks-down.sh"
}

cmd_help() {
  cat <<'EOF'
Cach dung: bash scripts/kltn.sh <lenh> [tham so]    (chay tu self-healing/)

Sim (khong can cum):
  setup               tao .venv (py -3.11 hoac python3.11), cai torch CPU + requirements, tao __init__.py
  test                pytest -q
  sanity              scripts/sanity_sim.py (noop vs rule, 7 kich ban)
  train               3 seed x (PPO, BC+PPO); STEPS mac dinh 300000
  promote [TAG]       copy models/TAG/best_model.zip -> models/current.zip (mac dinh bc_s0)
  ablation            huan luyen abl_nollm va abl_nofc
  sim-campaign        6 phuong phap + 3 ablation; REPS mac dinh 15
  analyze             analyze + plots
  sim-all             test -> train -> promote bc_s0 -> ablation -> sim-campaign -> analyze

Cum kind va port-forward:
  local-up            dung cum kind + stack (kubernetes/local/setup-local.sh)
  pf                  port-forward Prometheus 9090 + Locust 8089, bat tai nen 30 user
  pf-stop             dung cac port-forward do 'pf' khoi dong

Du lieu, hieu chinh, du bao, fine-tune:
  collect             thu du lieu offline (can GROQ_API_KEY); REPS mac dinh 6
  calibrate           hieu chinh Sim -> models/sim_params.json
  llm-eval [MODEL]    chay lai RCA tren MODEL (mac dinh openai/gpt-oss-120b; 'ollama' de chay cuc bo)
  forecast [all|export|train]   xuat du lieu va huan luyen LSTM (mac dinh all)
  finetune            fine-tune online (can GROQ_API_KEY); ROUNDS, EPISODES

Live, deploy, demo:
  live-campaign M     chien dich Live cho M = native|hpa|keda|rule|hybrid; REPS mac dinh 5
  live-all            lan luot native hpa keda rule hybrid
  image               docker build + kind load (IMAGE mac dinh hoangphuc858903/selfheal:dev)
  deploy              rbac + secret + controller.yaml + set image (can GROQ_API_KEY)
  demo                tiem su co; SCENARIO (mac dinh 3), TARGET (mac dinh frontend); cho cum on dinh truoc
                      (SKIP_STEADY=1 bo qua, STEADY_ONLY=1 chi kiem tra, STEADY_TIMEOUT=600)
  clean               don moi su co Chaos + tra tai nen ve 30 user

EKS:
  eks-up | eks-down   bat / tat cum EKS (terraform-modules/eks-up.sh, eks-down.sh)
EOF
}

#  dieu phoi 
cmd="${1:-help}"
if [ $# -gt 0 ]; then
  shift
fi

case "$cmd" in
  help|-h|--help) cmd_help ;;
  setup)          cmd_setup ;;
  test)           cmd_test ;;
  sanity)         cmd_sanity ;;
  train)          cmd_train ;;
  promote)        cmd_promote "$@" ;;
  ablation)       cmd_ablation ;;
  sim-campaign)   cmd_sim_campaign ;;
  analyze)        cmd_analyze ;;
  sim-all)        cmd_sim_all ;;
  local-up)       cmd_local_up ;;
  pf)             cmd_pf ;;
  pf-stop)        cmd_pf_stop ;;
  collect)        cmd_collect ;;
  calibrate)      cmd_calibrate ;;
  llm-eval)       cmd_llm_eval "$@" ;;
  forecast)       cmd_forecast "$@" ;;
  finetune)       cmd_finetune ;;
  live-campaign)  cmd_live_campaign "$@" ;;
  live-all)       cmd_live_all ;;
  image)          cmd_image ;;
  deploy)         cmd_deploy ;;
  demo)           cmd_demo ;;
  clean)          cmd_clean ;;
  eks-up)         cmd_eks_up ;;
  eks-down)       cmd_eks_down ;;
  *)
    echo "LOI: lenh khong hop le: '$cmd'" >&2
    cmd_help >&2
    exit 1
    ;;
esac