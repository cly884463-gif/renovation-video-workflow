import subprocess,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1];args=sys.argv[1:]
if not args:
 print('制作: configure init doctor voice align normalize assemble evidence validate preview render qa finalize')
 print('批次: batch inventory|review|deliver --config schedule.json --date YYYY-MM-DD')
 sys.exit(0)
script=root/'scripts/batch.py' if args[0]=='batch' else root/'engine/scripts/workflow.py'
sys.exit(subprocess.call([sys.executable,'-B',str(script)]+(args[1:] if args[0]=='batch' else args)))
