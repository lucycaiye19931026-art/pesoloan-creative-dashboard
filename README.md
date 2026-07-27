# Pesoloan双端各媒体素材表现看板

## 独立性
本项目为独立素材看板，不修改现有Pesoloan实时总看板及其第一、第二部分冻结模板。

## 地址
部署后页面：`/creative-dashboard`
数据接口：`/dashboard-api/creative-performance?month=YYYY-MM`

## 媒体范围
- Android：Google Ads、Facebook、TikTok
- iOS：Facebook、TikTok
- 所有金额统一为USD

## 筛选
- 月份
- 端口
- 媒体（iOS自动禁用Google）
- 素材类型：图片/视频
- 素材状态：当月新上/消耗蹿升

## 业务口径
当月新上：素材池中首次产生消耗的日期落在所选月份。

消耗蹿升必须同时满足：
1. 最近3个完整自然日日均消耗较此前3个完整自然日日均消耗上涨≥50%；
2. 最近3日总消耗≥$50；
3. 当月同端口、同媒体、同素材类型的消耗排名Top 10。

历史月份以该月最后3个自然日对比前3日；本月以昨天向前计算。

## 数据来源
- Facebook Marketing API：Ad级消耗、展示、点击；Ad Creative元数据和预览。
- TikTok Business API：Ad级日数据和广告元数据。
- Google Ads API：`ad_group_ad_asset_view`素材Asset级日数据。
- Adjust Report Service：`creative_network`维度的点击和放款归因。

CPS=`平台素材消耗÷Adjust素材loan数`；CR=`Adjust素材loan数÷Adjust素材归因点击数`。只有素材名匹配成功才显示CPS/CR；未匹配时显示“归因未匹配”，严禁模拟。

## 素材预览
- 图片：点击缩略图后打开高清原图。
- 视频：列表封面只用于识别，点击后必须在弹窗内动态播放，不得用静态截图代替视频。
- Facebook/TikTok使用平台返回的视频播放源，以HTML5播放器展示进度、音量和全屏控制。
- Google视频通过YouTube Video ID嵌入播放。
- 平台权限未返回播放源时明确显示“当前平台未返回可播放视频源”。关闭弹窗时必须停止播放。

## Render环境变量
复用现有：`FB_LONG_TOKEN`、`TT_ACCESS_TOKEN`、`TT_ADV_ID`、`TT_IOS_ADV_ID`、`GG_CLIENT_ID`、`GG_CLIENT_SECRET`、`GG_REFRESH_TOKEN`、`GG_DEVELOPER_TOKEN`、`GG_MCC_ID`、`ADJUST_APP_TOKEN`、`IOS_ADJUST_APP_TOKEN`、`ADJUST_USER_TOKEN`。

可选：
- `CREATIVE_POOL_START`：素材池起始日，默认`2026-06-01`。
- `CREATIVE_FB_ANDROID_IDS`、`CREATIVE_FB_IOS_IDS`、`GG_CUSTOMER_IDS`：逗号分隔；未配置时使用代码内非敏感账户清单。

## 独立部署（强制）
本项目必须上传到新GitHub仓库 `pesoloan-creative-dashboard`，并创建独立Render服务。严禁上传到原 `adjust-dashboard` 仓库，避免影响实时花费、余额预警和拒登看板。

新仓库根目录包含：
- `app.py`
- `creative_dashboard_module.py`
- `creative_dashboard.html`
- `requirements.txt`
- `render.yaml`
- `README.md`

启动命令：`gunicorn app:app --bind 0.0.0.0:$PORT --timeout 180`
健康检查：`/health`
看板页面：`/creative-dashboard`

首次请求需跨媒体拉取素材池历史数据，可能较慢；成功后缓存5分钟。接口会返回`errors`和`source_errors`，不得把采集失败解释为零素材。
