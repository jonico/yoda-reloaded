import subprocess, sys, collections
sys.path.insert(0,'/tmp/probe/yoda-b')
from yoda import lex
repo, enc = sys.argv[1], sys.argv[2]
files = subprocess.run(['git','-C',repo,'diff','--name-only','HEAD~1','HEAD'],
                       capture_output=True, text=True).stdout.split()
NORM = {'<':'>','<=':'>='}
bad = 0
for f in files:
    if not (f.endswith('.java') or f.endswith('.aj')): continue
    old = subprocess.run(['git','-C',repo,'show','HEAD~1:'+f],capture_output=True).stdout.decode(enc)
    new = open(repo+'/'+f, encoding=enc, newline='').read()
    def norm(src):
        return collections.Counter((t.kind, NORM.get(t.text, t.text)) for t in lex(src))
    if norm(old) != norm(new):
        bad += 1
        d = norm(old); d.subtract(norm(new))
        print('TOKEN MISMATCH', f, {k:v for k,v in d.items() if v})
print('%s: %d files checked, %d token-multiset mismatches' % (repo, len(files), bad))
