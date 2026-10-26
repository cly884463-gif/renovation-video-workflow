"""Local mount/migration regression; fixtures stay in an explicitly supplied new directory."""
import argparse
from pathlib import Path
from production import save, load_config, load_job
from contracts import source_key, approved
from source_paths import expand, roots


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args()
    out=Path(a.out).resolve();out.mkdir(parents=True,exist_ok=False)
    first=out/'offline';second=out/'mirror';other=out/'other'
    for root in (second,other):
        (root/'拍摄').mkdir(parents=True);(root/'扒扒').mkdir();(root/'文案').mkdir()
        (root/'拍摄/file.MOV').write_bytes(b'fixture')
    cfg=dict(_base=str(out),source_roots={'shared':[str(first),str(second)],'team':[str(other)]})
    cases=[]
    def check(name,ok):
        assert ok,name
        cases.append(name)
    def reject(name,fn):
        try:fn()
        except ValueError:cases.append(name)
        else:raise AssertionError(name)
    check('offline_primary_falls_back',Path(expand('@shared/拍摄/file.MOV',cfg))==second/'拍摄/file.MOV')
    check('directory_fallback',Path(expand('@shared/文案',cfg))==second/'文案')
    check('same_library_stable_identity',source_key(first/'拍摄/file.MOV',cfg)==source_key(second/'拍摄/file.MOV',cfg)=='@shared/拍摄/file.MOV')
    check('different_library_no_collision',source_key(other/'拍摄/file.MOV',cfg)=='@library/team/拍摄/file.MOV')
    check('named_library_expansion',Path(expand('@library/team/拍摄/file.MOV',cfg))==other/'拍摄/file.MOV')
    reject('unknown_library',lambda:expand('@library/unknown/file.MOV',cfg))
    reject('parent_traversal',lambda:expand('@shared/../other/拍摄/file.MOV',cfg))
    reject('absolute_escape',lambda:expand('@shared/'+str(other/'拍摄/file.MOV'),cfg))
    reject('missing_file',lambda:expand('@shared/absent.MOV',cfg))
    reject('outside_roots',lambda:source_key(out/'outside.MOV',cfg))
    reject('ambiguous_root_identity',lambda:roots(dict(source_roots={'shared':[str(second)],'team':[str(second)]})))
    check('legacy_shared_root',source_key(second/'拍摄/file.MOV',dict(shared_root=str(second)))=='@shared/拍摄/file.MOV')
    catalog={'presenters':{'person':dict(status='approved',source='@shared/拍摄/file.MOV')}}
    approved(catalog,'person',source_key(second/'拍摄/file.MOV',cfg),'presenters')
    cases.append('approval_survives_mount_change')
    reject('approval_not_inherited_by_other_library',lambda:approved(catalog,'person',source_key(other/'拍摄/file.MOV',cfg),'presenters'))
    c=dict(workspace='work',source_roots={'shared':['offline','mirror'],'team':['other']},material_roots=['@shared/扒扒','@shared/拍摄'],copy_root='@shared/文案')
    save(out/'machine.json',c);loaded=load_config(out/'machine.json')
    check('lazy_logical_directories',loaded['copy_root']=='@shared/文案' and loaded['material_roots'][0]=='@shared/扒扒')
    job=dict(copy=dict(source='@shared/拍摄/file.MOV'),voice={},music={},shots=[dict(source='@library/team/拍摄/file.MOV')])
    save(out/'job.json',job);loaded_job=load_job(out/'job.json',loaded)
    check('job_expands_both_libraries',loaded_job['copy']['source']==str(second/'拍摄/file.MOV') and loaded_job['shots'][0]['source']==str(other/'拍摄/file.MOV'))
    save(out/'result.json',dict(passed=True,cases=cases));print('PASS',len(cases),'source path regressions')


if __name__=='__main__':main()
