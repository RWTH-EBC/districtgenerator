#!/usr/bin/zsh
# Submit from the repository root: sbatch examples/slurm_bergfest_array.sh RUN_FOLDER
# Re-submission is safe after previous tasks have stopped: completed cases are skipped.
#SBATCH --job-name=bergfest
#SBATCH --account=thes2301
#SBATCH --partition=c23ms
#SBATCH --array=0-7%8
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=12G
#SBATCH --time=24:00:00
#SBATCH --mail-user=rawad.hamze@eonerc.rwth-aachen.de
#SBATCH --mail-type=END,FAIL
#SBATCH --output=districtgenerator/data/scenarios/Paper_3/optimization_runs/array_%A_%a.out
#SBATCH --error=districtgenerator/data/scenarios/Paper_3/optimization_runs/array_%A_%a.err

set -e
if [[ $# -lt 1 || $# -gt 2 || ! -f "$1/manifest.json" ]]; then
    print -u2 "Supply RUN_FOLDER and optionally --retry-failed-districts or --pilot."
    exit 2
fi
if [[ $# -eq 2 && "$2" != --retry-failed-districts && "$2" != --pilot ]]; then
    print -u2 "The optional argument is --retry-failed-districts or --pilot."
    exit 2
fi
ROOT="$SLURM_SUBMIT_DIR"
RUN_FOLDER="$1"
shift
types=(A B C D E F H I)
TYPE="${types[$((SLURM_ARRAY_TASK_ID + 1))]}"

module load GCCcore/13.3.0 Python/3.12.3 Gurobi/12.0.0
source "${ROOT:h}/venv/bin/activate"
export MPLCONFIGDIR="${ROOT:h}/matplotlib-cache"
export MPLBACKEND=Agg
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1

cd "$ROOT"
print "Settlement type: $TYPE; run folder: $RUN_FOLDER"
srun --cpu-bind=cores python -u examples/e8_bergfest_batch.py --resume "$RUN_FOLDER" --type "$TYPE" "$@"
