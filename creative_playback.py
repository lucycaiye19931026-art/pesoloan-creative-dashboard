"""单素材播放解析，不查询月报、不归档文件、不返回认证信息。
Usage: register_playback(app, config, FB_BASE, TT_BASE)
配置由Render环境提供；示例：gunicorn app:app --threads 4 --timeout 300
"""
import os
import re
import json
import requests
from flask import request, jsonify

SAFE_ID = re.compile(r'^[A-Za-z0-9_-]{1,160}$')

def fail(code, message):
    return {'ok': False, 'error_code': code, 'error': message}

def url(value):
    value = str(value or '').strip()
    if value.startswith('http://'):
        value = 'https://' + value[7:]
    return value if value.startswith('https://') else ''

class LookupErrorSafe(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message

def graph(base, object_id, fields):
    response = requests.get(base + '/' + object_id, params={
        'access_token': os.getenv('FB_LONG_TOKEN', ''), 'fields': fields
    }, timeout=(5, 15))
    body = response.json()
    error = body.get('error') or {}
    if response.status_code != 200 or error:
        code = error.get('code')
        if code == 190:
            raise LookupErrorSafe('AUTH_EXPIRED', 'Facebook授权已失效，需要维护人员更新Token')
        if code in (10, 200):
            raise LookupErrorSafe('PERMISSION_DENIED', '当前授权无权读取这条Facebook视频')
        raise LookupErrorSafe('OBJECT_UNAVAILABLE', 'Facebook对象无法读取：请核对广告归属、权限或是否已删除')
    return body

def video_ids(value):
    found = []
    def visit(node):
        if isinstance(node, dict):
            vid = str(node.get('video_id') or '')
            if vid.isdigit():
                found.append(vid)
            media_type = str(node.get('media_type') or node.get('type') or '').lower()
            target = node.get('target') or {}
            if 'video' in media_type and isinstance(target, dict):
                tid = str(target.get('id') or '')
                if tid.isdigit(): found.append(tid)
            for child in node.values(): visit(child)
        elif isinstance(node, list):
            for child in node: visit(child)
    visit(value)
    return list(dict.fromkeys(found))

def facebook(spec, config, base):
    account = str(spec.get('account_id') or '').replace('act_', '')
    if account not in set(config()['fb_android'] + config()['fb_ios']):
        return fail('ACCOUNT_NOT_ALLOWED', '该Facebook账户未配置，拒绝查询')
    ad_id = str(spec.get('ad_id') or '')
    creative_id = str(spec.get('creative_id') or '')
    direct_id = str(spec.get('video_id') or '')
    if ad_id.isdigit():
        ad = graph(base, ad_id, 'id,account_id,creative{id}')
        if str(ad.get('account_id') or '').replace('act_', '') != account:
            return fail('ACCOUNT_MISMATCH', '广告不属于指定Facebook账户')
        creative_id = str((ad.get('creative') or {}).get('id') or '')
    elif creative_id.isdigit():
        # 旧月报可能缺少Ad ID：先验证Creative确实属于账户，禁止跨账户查询。
        response = requests.get(base + '/act_' + account + '/adcreatives', params={
            'access_token': os.getenv('FB_LONG_TOKEN', ''), 'fields': 'id',
            'filtering': json.dumps([{'field': 'id', 'operator': 'IN', 'value': [creative_id]}]), 'limit': 100
        }, timeout=(5, 15))
        body = response.json()
        if response.status_code != 200 or creative_id not in {str(x.get('id')) for x in body.get('data', [])}:
            return fail('CREATIVE_NOT_VERIFIED', '旧月报缺少广告ID，无法验证创意归属；请补Ad ID或重新生成该账户快照')
    else:
        return fail('IDENTIFIER_MISSING', 'Facebook月报记录缺少广告ID和Creative ID')
    if not creative_id.isdigit():
        return fail('IDENTIFIER_MISSING', '该广告未返回Creative ID')
    creative = graph(base, creative_id, 'id,thumbnail_url,video_id,object_story_spec,asset_feed_spec,effective_object_story_id')
    ids = video_ids(creative)
    story = str(creative.get('effective_object_story_id') or '')
    if not ids and re.fullmatch(r'[0-9_]+', story):
        try:
            post = graph(base, story, 'attachments{media_type,type,target,subattachments{media_type,type,target}}')
            ids = video_ids(post)
        except LookupErrorSafe:
            return fail('POST_VIDEO_UNAVAILABLE', '帖子引用视频无法读取，需要该主页视频读取权限或原始文件')
    if direct_id and direct_id in ids: ids = [direct_id]
    if not ids:
        return fail('VIDEO_ID_MISSING', '创意、动态素材及帖子中均未找到可验证的视频ID')
    variants, errors = [], []
    for vid in ids[:20]:
        try:
            video = graph(base, vid, 'id,source,picture,permalink_url')
            source = url(video.get('source'))
            if source:
                variants.append({'video_id': vid, 'media_url': source,
                    'preview_url': url(video.get('picture') or creative.get('thumbnail_url')),
                    'player_type': 'video'})
            else: errors.append(fail('SOURCE_UNAVAILABLE', 'Facebook未开放原视频播放源，需补授权或原始视频'))
        except LookupErrorSafe as exc: errors.append(fail(exc.code, exc.message))
    if not variants: return errors[0] if errors else fail('SOURCE_UNAVAILABLE', '没有可播放的视频')
    return {'ok': True, 'platform': 'facebook', 'variants': variants, 'warnings': errors, **variants[0]}

def tiktok(spec, config, base):
    account = str(spec.get('account_id') or '')
    if account not in set(config()['tt_android'] + config()['tt_ios']):
        return fail('ACCOUNT_NOT_ALLOWED', '该TikTok账户未配置')
    headers = {'Access-Token': os.getenv('TT_ACCESS_TOKEN', '')}
    vid = str(spec.get('video_id') or '')
    if not vid:
        ad_id = str(spec.get('ad_id') or spec.get('creative_id') or '')
        if not ad_id.isdigit(): return fail('IDENTIFIER_MISSING', '记录缺少真实Video ID和Ad ID')
        r = requests.get(base + '/ad/get/', headers=headers, timeout=(5, 15), params={
            'advertiser_id': account, 'filtering': json.dumps({'ad_ids': [ad_id]}), 'page_size': 10})
        body = r.json()
        if body.get('code') != 0: return fail('AD_LOOKUP_FAILED', 'TikTok广告关系查询失败，错误码：' + str(body.get('code')))
        ad = next((x for x in (body.get('data') or {}).get('list', []) if str(x.get('ad_id')) == ad_id), {})
        vid = str(ad.get('video_id') or '')
    if not SAFE_ID.fullmatch(vid): return fail('VIDEO_ID_MISSING', '未找到可验证的真实TikTok Video ID，不按名称猜测')
    r = requests.get(base + '/file/video/ad/info/', headers=headers, timeout=(5, 20), params={
        'advertiser_id': account, 'video_ids': json.dumps([vid])})
    body = r.json()
    if body.get('code') != 0:
        return fail('VIDEO_LOOKUP_FAILED', 'TikTok视频读取失败，错误码：' + str(body.get('code')) + '；请核对权限和视频归属')
    videos = (body.get('data') or {}).get('list', [])
    video = next((x for x in videos if str(x.get('video_id')) == vid), {})
    source = url(video.get('preview_url') or video.get('play_url') or video.get('video_url'))
    if not source: return fail('SOURCE_UNAVAILABLE', 'TikTok未返回该视频播放地址，请核对视频是否删除或补原始文件')
    return {'ok': True, 'platform': 'tiktok', 'video_id': vid, 'media_url': source,
        'preview_url': url(video.get('video_cover_url') or video.get('cover_url') or video.get('poster_url')), 'player_type': 'video'}

def register_playback(app, config, fb_base, tt_base):
    @app.route('/dashboard-api/creative-playback', methods=['POST'])
    def creative_playback():
        spec = request.get_json(silent=True)
        if not isinstance(spec, dict): return jsonify(fail('INVALID_REQUEST', '请求必须是单条素材JSON')), 400
        platform = str(spec.get('channel') or spec.get('platform') or '').lower()
        try:
            if platform == 'facebook': result = facebook(spec, config, fb_base)
            elif platform == 'tiktok': result = tiktok(spec, config, tt_base)
            else: result = fail('UNSUPPORTED_PLATFORM', '该接口仅解析Facebook/TikTok，Google使用YouTube播放器')
        except LookupErrorSafe as exc: result = fail(exc.code, exc.message)
        except requests.Timeout: result = fail('UPSTREAM_TIMEOUT', '平台取源超时，请点击重试；未重新采集月报')
        except Exception: result = fail('LOOKUP_FAILED', '单视频取源失败，请检查服务日志中的脱敏错误')
        response = jsonify(result)
        response.headers['Cache-Control'] = 'private, no-store'
        return response, 200 if result.get('ok') else 422
