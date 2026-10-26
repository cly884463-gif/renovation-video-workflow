"""V3 gates: evidence integrity, exact approval scope, and input-version binding."""
from pathlib import Path
from production import read,sha,require,canon,text_hash

def source_key(source,cfg):
    p=Path(source).resolve()
    for item in cfg.get('source_mappings',[]):
        if Path(item['path']).resolve()==p:
            require(sha(p)==item['sha256'] and item.get('basis'),'云端缓存映射缺哈希或真实来源依据')
            require(item['source_key'].startswith('@cloud/'),'额外源映射仅支持准确云端ID，不能重命名共享审批源')
            return item['source_key']
    from source_paths import key
    return key(source,cfg)

def approved(catalog,identifier,key,kind):
    entries=catalog[kind];require(identifier in entries,'审批ID不存在：'+str(identifier))
    x=entries[identifier];require(x['status']=='approved','审批未通过')
    target=x['source'];scope=x.get('scope','exact')
    require(key==target or (scope=='project' and key.startswith(target.rstrip('/')+'/')),'审批与准确源文件/项目范围不匹配')

def validate_evidence(job,cfg):
    require(job.get('schema_version')==3,'旧版job不可直接制作；按v3证据流程迁移，旧成片不受影响')
    from source_paths import roots
    require(roots(cfg) and cfg.get('approvals'),'缺素材库根或审批清单')
    catalog=read(cfg['approvals'])
    report=read(job['voice']['alignment_file'])
    require(report.get('passed') is True and report.get('audio_sha256')==sha(job['voice']['path']) and report.get('text_sha256')==job['copy']['sha256'],'配音识别证据不对应当前音轨/文字')
    require(report.get('expected')==canon(job['copy']['text']),'ASR期望文本不一致')
    from align import compare
    compare(report['expected'],report['recognized'],report['differences'])
    require(sha(job['voice']['asr_result_file'])==report['result_sha256'],'原始ASR结果变化')
    require(canon(read(job['voice']['asr_result_file'])[0]['text'])==report['recognized'],'ASR记录不一致')
    require(sha(job['voice']['captions_file'])==report['captions_sha256'] and read(job['voice']['captions_file'])==job['captions'],'字幕不对应已对齐版本；显示修改后重新对齐，可导入同音轨ASR')
    evidence=read(job['review_file']);require(len(evidence['shots'])==len(job['shots']),'镜头审核数量不符')
    from evidence import binding
    source_hashes={}
    for i,(s,r) in enumerate(zip(job['shots'],evidence['shots'])):
        provenance=read(s['provenance_file'])
        source=Path(s['source']).resolve()
        if source not in source_hashes:source_hashes[source]=sha(source)
        require(Path(provenance['source']).resolve()==source and provenance['source_sha256']==source_hashes[source] and provenance['source_start']==s['source_start'] and provenance['source_duration']==s['source_duration'] and provenance['sha256']==sha(s['path']),'规范化来源、区间或文件不对应；用normalize重新生成，禁止手填绕过')
        require(r['shot_index']==i and r['binding']==binding(s),'镜头输入/区间/顺序/意图变更，请重新生成审核证据')
        require(r.get('status')=='accepted' and r.get('reviewer') and r.get('note'),'镜头必须逐项实视填写审核')
        require(isinstance(r.get('semantic_score'),(int,float)) and not isinstance(r['semantic_score'],bool) and 80<=r['semantic_score']<=100,'语义评分须为80–100分')
        artifacts=r['artifacts'];needed={0,(s['frames']+(6 if i+1<len(job['shots']) and job['shots'][i+1]['transition']=='dissolve' else 0)-1)}
        require(needed.issubset({a['frame'] for a in artifacts}),'缺首尾及转场运动余量证据')
        require(len(artifacts)>=3,'缺首中尾证据')
        for a in artifacts:require(sha(a['path'])==a['sha256'],'审核截图缺失或变更')
        key=source_key(s['source'],cfg)
        require(not any(key==x for x in catalog.get('excluded_people_sources',[])),'人物源已被用户排除')
        require(Path(s['source']).stem.split('_')[0] not in set(catalog.get('excluded_people_source_ids',[])),'人物源编号已被用户排除，不能由相似人物放行')
        people=r.get('people_kind');require(people in ('approved_presenter','no_identifiable_face','worker_nonidentifying'),'人物审核类型缺失')
        if people=='approved_presenter':approved(catalog,r.get('presenter_approval_id'),key,'presenters')
        material=r.get('material_kind');require(material in ('micro_ceramic_mud','generic_service','counterexample','city'),'材料审核类型缺失')
        if material=='micro_ceramic_mud':
            require(key not in catalog.get('excluded_material_sources',[]),'材料源已被否认')
            approved(catalog,r.get('material_approval_id'),key,'materials')
        if s.get('names_presenter'):require(people=='approved_presenter','点名出镜人必须绑定批准人物源')
        if s.get('asserts_material'):require(material=='micro_ceramic_mud','材料工序/效果断言必须绑定材料审批')
    require(job.get('presenter_selection_note'),'缺出镜人物优先选镜记录；这是偏好而非固定配额，不能凑数')
