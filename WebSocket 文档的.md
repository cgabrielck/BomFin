本服务支持美股与期权行情数据接入，包括 WebSocket 实时行情和 REST API 查询。
主要支持：
- 美股实时 Trades
- 美股实时 Quotes
- 美股实时 Aggregates
- 期权具体合约实时 Trades
- 期权具体合约实时 Quotes
- 期权具体合约实时 Aggregates
- REST API 数据查询
- REST 全市场股票 Snapshot
- REST 全市场股票每日汇总 K 线，即 Grouped Daily
- REST 对应上游接口支持的多标的批量查询
- REST 期权链 Snapshot 分页查询
- REST 股票 IPO 信息查询
- REST 股票标的事件查询，即 Ticker Events
以上为服务整体支持范围。客户实际可访问的数据，以购买并开通的产品权限为准：
- 股票单订阅：Stocks WebSocket＋服务允许的 Stocks REST 接口。
- 期权单订阅：具体期权合约 WebSocket＋服务允许的 Options REST 接口。
- 双订阅：同时包含 Stocks 和 Options 权限。

WebSocket 适合接收实时推送数据。
REST API 适合查询历史 K 线、成交、报价、聚合行情、全市场股票 Snapshot、股票每日市场汇总、单标的 Snapshot、期权链 Snapshot、单期权合约 Snapshot、股票 IPO 信息、股票标的事件，以及其他已开通产品范围内、上游权限支持且服务允许转发的 Stocks 或 Options REST 数据。
需要区分：
- 全市场股票某一天的日线，可以通过 Grouped Daily 接口一次查询。
- 全市场股票 Snapshot 可以返回各股票的最新行情及最近分钟汇总等字段。
- 全市场股票一段时间内的完整历史分钟线，仍需要按股票逐个查询并自行汇总，一次 Snapshot 请求不能获取全部历史分钟线。
- 整条期权链通常是指某个标的的期权链，例如 SPY、AAPL 或 SPX 的期权链，需要按接口规则分页。
本服务仅提供 Stocks 和 Options 范围内的数据。不开放独立的 Futures、Indices、Forex、Crypto 等其他资产类别接口，也不提供 Flat Files 下载服务。
指数期权链 Snapshot 属于 Options 数据，例如：
/v3/snapshot/options/I:SPX
/v3/snapshot/options/I:NDX
此类路径中的 I: 表示期权链的底层标的。期权单订阅和双订阅客户可在服务允许的范围内查询，实际可返回的字段和历史范围仍取决于上游数据与权限。
二、接入地址说明
请先在 PickAlphas「我的数据服务」中确认自己开通的是美国 1 号还是美国 2 号，展开接入信息，复制该节点的地址和专属 Key。 客户应使用实际开通节点的域名，Key 不跨节点通用。
WebSocket 实时行情使用 wss://，REST 行情和授权查询使用 https://。同一节点的三个入口共用一个域名，均使用默认加密端口 443，地址中无需填写端口号。

WebSocket 地址：wss://<MASSIVE_HOST>/ws?key=你的Key
REST API 地址：https://<MASSIVE_HOST>
授权与用量查询：https://<MASSIVE_HOST>/my-license

本文后续示例统一使用美国 1 号。美国 2 号客户请将示例中的 massive-1.pickalphas.com 替换为 <MASSIVE_HOST>。 你的Key 请替换为本人在该节点开通的客户 Key。
REST 请求时，将具体接口路径直接接在所属节点域名后面。以下为美国 1 号的股票 K 线示例，需要股票单订阅或双订阅权限：
https://massive-1.pickalphas.com/v2/aggs/ticker/AAPL/range/1/minute/2026-06-01/2026-06-02
注意：
- WebSocket 使用 /ws?key=你的Key 建立连接。
- REST 行情查询将 Key 放在请求头中。`/my-license` 授权与用量查询使用 X-Proxy-Key 请求头。
- 原先使用 IP 地址的客户，切换时请替换完整地址，继续使用原 Key。 新域名后面不要保留旧地址的 :8080 或 :8081。原有接口路径、订阅参数和套餐额度继续适用。
- 旧 IP 明文地址目前保留兼容。程序中仍配置旧地址的客户，需要主动改为上述 wss:// 或 https:// 地址，才能使用加密连接。
- 不要公开自己的 Key，或将包含 Key 的完整连接地址提交到公开代码仓库。

套餐一　单订阅 99 元/30 天，双订阅 198 元/30 天
- WebSocket：单订阅最多 50 个订阅参数，双订阅最多 100 个订阅参数。
- 套餐每 30 天账期总流量：单订阅最多 120 GiB，双订阅最多 240 GiB，WebSocket 和 REST API 共用。
- REST：单订阅和双订阅均为每分钟最多 1000 次请求。
- REST：不设置代理端单次查询时间跨度上限，实际历史范围取决于上游数据与权限。
- REST：每日流量不限，但仍计入当前 30 天账期总流量。
- 单订阅和双订阅均限 1 个 WebSocket 连接。
适合核心股票或具体期权合约实时监控。需要同时使用股票和期权时，请选择双订阅。

WebSocket 接入说明
连接成功后，发送订阅请求。
股票单订阅或双订阅客户的股票订阅示例：
{"action":"subscribe","params":"T.AAPL,Q.AAPL"}
期权单订阅或双订阅客户的期权订阅示例：
{"action":"subscribe","params":"T.O:SPY261218C00650000,Q.O:SPY261218C00650000"}
示例中的期权合约仅用于说明格式，请替换为实际需要且有效的具体合约。
订阅成功后，在有相应行情更新时会持续收到实时行情推送。
套餐一和套餐二的同一个 Key 只允许保持 1 条 WebSocket 连接。套餐三的同一个 Key 最多允许保持 2 条 WebSocket 连接，两条连接共享该 Key 的订阅参数额度和账期总流量。
双订阅客户可以在同一条 WebSocket 连接里同时订阅股票和期权。单订阅客户只能订阅已开通的资产类别。
套餐一和套餐二正确用法
双订阅客户在同一条连接中发送：
{"action":"subscribe","params":"T.MU,Q.MU,T.O:SPY261218C00650000,Q.O:SPY261218C00650000"}
股票单订阅客户只发送股票参数，期权单订阅客户只发送具体期权合约参数。
如果一次订阅请求同时包含有权限和无权限的资产参数，整条订阅请求会被拒绝。
套餐一和套餐二错误用法
连接 1：订阅股票
连接 2：订阅期权
即使购买了双订阅，这种方式也会触发同一个 Key 的连接数限制。

断线与重连
服务更新、网络故障、客户端消费过慢、授权到期、产品权限变更或流量超限等情况可能导致连接关闭。
客户端应自行实现断线处理和重连逻辑。建立新连接后，需要重新发送当前希望订阅的参数。重连不能绕过产品权限、授权到期、流量额度或连接数限制。
五、订阅参数说明
订阅参数按逗号分隔计数。
T.AAPL     算 1 个订阅参数
Q.AAPL     算 1 个订阅参数
A.AAPL     算 1 个订阅参数
AM.AAPL    算 1 个订阅参数

T.AAPL,Q.AAPL,A.AAPL             合计 3 个订阅参数
T.AAPL,Q.AAPL,AM.AAPL            合计 3 个订阅参数
T.AAPL,Q.AAPL,A.AAPL,AM.AAPL     合计 4 个订阅参数
常见类型
T.AAPL     美股逐笔成交
Q.AAPL     美股实时报价
A.AAPL     美股秒级聚合行情
AM.AAPL    美股分钟聚合行情
A 与 AM 是不同的订阅类型。只订阅 AM.AAPL 不表示同时订阅 A.AAPL。
期权必须订阅具体合约，例如：
T.O:SPY261218C00650000
Q.O:SPY261218C00650000
具体可用频道和行情更新情况取决于上游对该资产的支持，以及当前 Key 已开通的产品权限。
套餐三使用两条连接时，两条连接的订阅参数合并计算。如果同一个参数在套餐三两条连接中重复订阅，该参数只占用 1 个订阅参数名额，但行情会分别发送到两条连接，因此产生的传输流量会按两份计算。
同一股票或合约订阅多个频道，会占用多个参数名额。双订阅的股票和期权参数共同使用该 Key 的订阅参数额度。
本节限制仅适用于 WebSocket 实时订阅。REST 单次响应可以包含多少只股票或多少期权合约，取决于其接口规则，同时受请求频率、并发和账期流量限制。
六、参考流量样本
以下为历史实际测试样本，仅供参考。不同交易时段、不同标的活跃度、不同市场波动下，消息速度和带宽都会变化。
以下“条/秒”为样本统计口径，不代表固定事件速率或套餐限制。一条 WebSocket 消息可能包含多个行情事件。
股票实时 Trades / Quotes 样本
测试订阅：MU、TSLA、SPY、NVDA 的 Trades＋Quotes。
合计：约 606 条消息/秒，约 89.8 KB/秒。
如果只在美股正常交易时段运行，按每月约 22 个交易日、每天 6.5 小时估算：
约 45–50 GB/月
如果盘前盘后也长时间运行，月流量可能接近或超过：
100 GB/月
以上为历史样本的粗略估算，实际用量以 /my-license 返回的 GiB 数值为准。
其中较活跃的标的样本：
MU trades      约 166 条/秒
NVDA trades    约 117 条/秒
SPY quotes     约 89 条/秒
NVDA quotes    约 71 条/秒
TSLA trades    约 65 条/秒
MU quotes      约 50 条/秒
TSLA quotes    约 30 条/秒
SPY trades     约 17 条/秒
期权实时 Trades / Quotes 样本
测试订阅：14 个 SPY／TSLA／NVDA 附近活跃合约，期权 Trades＋Quotes。
合计：约 242 条消息/秒，约 29.5 KB/秒。
期权 Quotes-only 样本
测试订阅：10 个活跃期权合约，只订阅 Quotes。
合计：约 149 条消息/秒，约 18.5 KB/秒。
说明
- 热门股票同时订阅 Trades＋Quotes 时，事件速度可能比较高。
- 三档套餐的单订阅和双订阅均不设置持续事件速率和短时突发池限制。
- 订阅多个热门标的时，实际带宽和流量消耗可能明显增加，更快用完当前账期额度。
- 客户端应持续读取 WebSocket，并及时处理消息，避免因消费过慢产生积压。
- WebSocket 期权实时行情需要订阅具体合约。
- REST 可以分页查询某个标的的整条期权链 Snapshot。
- 活跃合约的 Quotes 更新频率可能明显高于不活跃合约。
- 全市场股票快照、Grouped Daily 或整条期权链查询可能产生较大的单次 REST 响应。
- 以上样本仅用于理解大致量级，不代表未来固定流量或固定事件速度。
七、WebSocket 使用限制
不支持全市场订阅，例如：
T.*
Q.*
A.*
AM.*
*
不支持期权全链 Quotes，例如：
Q.O:SPY*
期权必须订阅具体合约。
股票单订阅不能订阅期权，期权单订阅不能订阅股票。未开通资产的订阅请求会被拒绝。如果一次订阅请求混合了允许和禁止的资产参数，整条请求会被拒绝，也不会占用新增订阅参数额度。
超过套餐订阅参数上限，订阅请求会被拒绝。
三档套餐不设置持续 events/s 限制，也不设置短时突发池限制，不再按原套餐事件速率丢弃超出部分行情。服务仍保留以下限制与保护：
- 当前 Key 已开通的产品权限
- 同一个 Key 的 WebSocket 连接数限制
- 订阅参数数量限制
- 当前账期总流量限制
- 每连接有界发送队列
- 写入超时与慢客户端保护
- 授权状态及服务到期检查
客户端消费过慢或网络持续阻塞时，发送队列可能积压。为避免无限占用服务器资源，服务可能丢弃积压消息或关闭该连接，不保证补发旧行情。
WebSocket 与 REST API 的响应流量共同计入同一个 Key 的当前 30 天账期总流量。
达到当前账期总流量上限后，服务会拒绝受额度限制的请求或关闭相关连接。进入下一 30 天账期、额度重置且授权仍有效后，可重新访问。
提前续费会延长服务到期时间，但不会立即重复增加或重置当前尚未结束的账期流量额度。如果套餐已经到期后重新续费，则从重新开通时间开始建立新的 30 天账期和流量额度。
单／双订阅或套餐档位发生变更时，额度按变更后的授权计算，已累计的账期用量不会因变更而清零。实际产品权限、账期和剩余额度以 /my-license 查询结果为准。
REST 全市场、批量查询限制的解除，不改变本节的 WebSocket 限制。
八、REST API 接入说明
REST API 使用客户 Key 鉴权。请求时需要在 Header 中携带 Key：
X-Proxy-Key: 你的Key
或：
X-API-KEY: 你的Key
REST API 保持上游接口的路径和参数形式。将请求地址换成所属节点的 HTTPS 地址，并携带自己的 Key。
REST API 仅开放服务允许转发的 Stocks 和 Options 接口，并根据当前 Key 的产品权限进一步限制：
- 股票单订阅：可访问允许的 Stocks REST 接口，包括全市场股票 Snapshot、Grouped Daily、IPO 信息和股票标的事件查询。
- 期权单订阅：可访问允许的 Options REST 接口，包括期权链 Snapshot 分页查询。
- 双订阅：可访问允许的 Stocks 和 Options REST 接口。
能否获得数据同时取决于已开通产品、上游权限、历史覆盖范围、接口支持和服务限制。
期权链 Snapshot 中可能包含标的相关字段，这不代表期权单订阅同时获得了独立的股票或指数接口权限。
查询 /v3/reference/tickers 时，期权单订阅客户未指定 market 则默认按 market=options 查询。股票单订阅和双订阅客户未指定时默认按 market=stocks 查询。双订阅客户如需查询期权，应显式指定 market=options。
注意：
- REST 行情查询的 Key 放在 Header 里。
- 本文 WebSocket 示例将 Key 放在 wss:// 连接 URL 里。
- /my-license 授权查询使用 Header 中的 X-Proxy-Key。
- 请使用卖家提供的客户 Key，不要使用上游 Massive Key。

股票标的事件查询
股票单订阅和双订阅客户可查询上游提供的股票标的事件。实际事件类型和覆盖范围以上游返回为准。
接口路径：
/vX/reference/tickers/{id}/events
请保留版本名称中的大写 X。`{id}` 可使用股票代码或上游支持的 CUSIP、Composite FIGI。
请求地址示例：
https://massive-1.pickalphas.com/vX/reference/tickers/META/events
请求时在 Header 中携带自己的客户 Key。该接口属于 Stocks 数据，期权单订阅不能访问。
客户授权与用量查询
客户可以使用自己的 Key 查询当前套餐、产品权限、服务到期时间和流量使用情况。
查询地址：
美国 1 号：https://massive-1.pickalphas.com/my-license
美国 2 号：https://<MASSIVE_HOST>/my-license
请求时需要在 Header 中携带：
X-Proxy-Key: 你的Key
curl 示例
curl "https://massive-1.pickalphas.com/my-license" \
  -H "X-Proxy-Key: 你的Key"
Python 示例
import requests

url = "https://massive-1.pickalphas.com/my-license"
headers = {"X-Proxy-Key": "你的Key"}

response = requests.get(url, headers=headers, timeout=10)
print(response.status_code)
if response.ok:
    print(response.json())
else:
    print(response.text)


返回内容包括：
- 套餐代码和账号状态
- 当前 Key 已开通的产品权限
- 当前单／双订阅组合的 30 天标准价格
- 服务到期时间
- 当前 30 天流量账期的开始时间和结束时间
- 当前账期总流量额度
- WebSocket 与 REST 合计已使用流量
- 当前账期剩余流量
- WebSocket 订阅参数上限
- WebSocket 事件速率限制是否启用
- WebSocket 最大连接数
- REST 每分钟请求上限
- REST 每日流量限制是否启用
常用返回字段
plan                              套餐代码
products                          已开通的产品权限
status                            账号状态
price_cny_30_days                 当前产品组合的 30 天标准价格，单位为人民币元
expires_at                        服务到期时间
traffic_cycle_start               当前流量账期开始时间
traffic_cycle_end                 当前流量账期结束时间
monthly_traffic_gib               当前账期总流量额度
traffic_used_gib                  当前账期已使用流量
traffic_remaining_gib             当前账期剩余流量
subscription_param_limit          WebSocket 订阅参数上限
event_rate_limit_enabled          是否启用套餐级事件速率限制
message_limit_per_second          持续事件速率字段，当前为 0，表示不限制
event_burst_capacity              短时突发池字段，当前为 0，表示不限制
max_connections                   WebSocket 最大连接数
rest_requests_per_minute          REST 每分钟请求上限
rest_daily_traffic_gib            REST 每日流量上限，当前为 null，表示不限制
rest_daily_traffic_limit_enabled  是否启用 REST 每日流量限制，当前为 false

套餐代码对应关系：
advance_ws_200    套餐一
advance_ws_300    套餐二
advance_ws_600    套餐三
同一套餐代码适用于单订阅和双订阅，请结合 products 判断产品权限，并以返回的实际额度为准。
产品权限对应关系：
["stocks"]               股票单订阅
["options"]              期权单订阅
["stocks", "options"]    股票＋期权双订阅
当前三档套餐的事件速率相关字段均为：
{
  "event_rate_limit_enabled": false,
  "message_limit_per_second": 0,
  "event_burst_capacity": 0
}
这里的 0 表示不设置套餐级事件速率或突发池限制，仍可正常接收行情。
当前三档套餐的 REST 每日流量相关字段均为：
{
  "rest_daily_traffic_gib": null,
  "rest_daily_traffic_limit_enabled": false
}
这里的 null 和 false 表示不设置 REST 每日流量上限。REST 流量仍会计入当前 30 天账期总流量。
注意：
- /my-license 与 REST 行情接口共用所属节点的 HTTPS 域名。查询授权时使用 /my-license，查询行情时使用对应的行情接口路径。
- 该接口只能查询当前 Key 自己的信息。
- 已使用流量为 WebSocket 与 REST 在当前 30 天账期内的合计用量。
- 当前接口不提供历史账期或逐日用量明细，也不单独显示北京时间当日的 REST 流量使用量。
- price_cny_30_days 表示当前套餐与产品组合的 30 天标准价格，历史订单实付金额以订单记录为准。
- 返回时间应根据其时区信息转换。如需北京时间，可转换为 UTC+8。
- Key 无效、已停用或已经过期时，查询会被拒绝。
- REST 并发规则见第九节“REST 使用限制”。
REST 压缩传输
REST API 支持 gzip 压缩传输。压缩与未压缩方式使用同一个接口地址，解压后获得的数据内容一致。
接受 gzip 压缩时，在 Header 中携带：
Accept-Encoding: gzip
需要未压缩数据时，在 Header 中携带：
Accept-Encoding: identity
未显式设置 Accept-Encoding 时，客户端库可能自动添加该请求头。需要确定传输方式时，请显式指定 gzip 或 identity。
Python requests 等常见客户端通常会自动协商压缩并自动解压，因此原有 response.text、`response.json()` 等读取方式无需修改。
服务器实际采用 gzip 返回时，响应头中会包含：
Content-Encoding: gzip
如果客户端自动解压，程序中读取到的正文大小可能大于网络传输大小。gzip 响应按发送时的压缩正文大小计量。
九、REST 使用限制
REST API 统一受以下限制：
- 仅开放服务允许转发且当前 Key 已开通权限的 Stocks 或 Options 数据接口。
- Flat Files 批量文件下载仍不开放。
- REST 响应流量同时计入套餐当前 30 天账期总流量。
- 单次请求有超时限制。
- 需要分页的接口仍应按上游规则分页。
- 同一客户在同一服务节点的股票和期权 REST 并发分别计算，每类最多同时处理 10 笔。
- 频率或账期流量超限会返回 429。服务繁忙或请求等待超时时，可能返回 503。
当前已解除以下 REST 查询的代理禁止规则：
- 全市场股票 Snapshot。
- 全市场股票每日汇总 K 线，即 Grouped Daily。
- 对应上游接口支持的多标的批量参数。
- 通配符查询参数的代理拦截。
具体接口支持的参数、筛选方式和返回内容，仍以上游接口规则为准。例如：
/v2/snapshot/locale/us/markets/stocks/tickers?tickers=AAPL,TSLA

/v3/snapshot?ticker.any_of=AAPL,TSLA
以上是不同接口的批量查询方式，参数名称应按具体接口选用。
对于股票代码范围筛选，可以使用上游支持的形式，例如：
/v3/snapshot?type=stocks&ticker.gte=A&ticker.lt=B
ticker=A* 不保证可用。历史测试中，上游股票列表接口对此写法返回 400。
精确 ticker 列表示例：
/v3/snapshot?ticker.any_of=AAPL,TSLA
不要额外附加不受该接口支持的 type 参数组合，否则上游可能返回 400。
同一批次同时请求股票和期权数据，需要双订阅权限。单订阅不能通过批量查询绕过资产权限限制。
WebSocket 的订阅参数数量限制不适用于 REST 单次返回数量。REST 一次全市场查询虽然只计一次请求，但响应数据会按实际大小计入账期流量。
REST 并发说明
- 股票单订阅：同一客户在同一服务节点最多同时处理 10 笔股票 REST 请求。
- 期权单订阅：同一客户在同一服务节点最多同时处理 10 笔期权 REST 请求。
- 双订阅：股票与期权并发独立计算，可同时处理最多 10 笔股票请求＋10 笔期权请求。
- 单笔请求同时查询股票和期权时，占用两类并发额度各 1 笔。该请求仍按一笔 REST 请求计入每分钟请求次数。
- 同一客户在同一节点使用多个进程、设备或同类授权时，按该产品合计控制并发。建议客户端等同类请求完成后，再发送下一笔。
- 达到对应产品的并发上限时，后续请求可能需要等待。服务繁忙或等待超时时，可能返回 503，处理方式见第十二节。
每分钟 REST 请求次数按套餐限制：
- 套餐一：每分钟最多 1000 次。
- 套餐二：每分钟最多 1000 次。
- 套餐三：每分钟最多 1500 次。
同一档位的单订阅与双订阅使用相同的每分钟请求上限，双订阅不会将请求频率额度翻倍。并发上限和每分钟请求上限同时生效。
REST 每日流量说明
- 套餐一：每日流量不限。
- 套餐二：每日流量不限。
- 套餐三：每日流量不限。
REST 与 WebSocket 仍共同使用当前 Key 的 30 天账期总流量额度。同一个 Key 的 REST 请求共同使用该 Key 的额度，不会因为多个进程或多个设备发起请求而增加额度。
服务仍按北京时间自然日记录 REST 日用量。北京时间每日 00:00 进入新的日用量统计日期，不会重置当前 30 天账期总流量。
例如 Insider Trades、Short Volume、财报、基本面等研究类接口，如果属于当前 Key 已开通且服务允许的 Stocks 或 Options 范围、上游权限支持、接口已开放转发，并且符合请求频率、并发、账期流量和超时规则，可以按需使用。
全市场股票日线可以通过 Grouped Daily 按日期查询。完整历史分钟线仍按具体股票查询，客户可以逐只股票获取并自行汇总。
上游服务故障、权限限制或上游自身限流，也可能影响请求。即使请求符合套餐额度和并发限制，仍可能遇到上游错误或超时。

REST 流量计量说明
REST 日用量统计和当前 30 天账期总流量扣量，均按服务器发送的响应正文大小计量：
- gzip 压缩响应：按压缩后的正文大小计量。
- 未压缩响应：按未压缩正文大小计量。
- 不包含 HTTP 响应头和 TCP/IP 等网络协议开销。
- 客户端在本地解压后的数据大小，不作为压缩响应的扣量依据。
例如，同一份 JSON 原文为 7 MB，压缩后实际发送 0.8 MB，则计量约 0.8 MB。如果选择未压缩传输，则计量约 7 MB。实际压缩比例随数据内容变化，不保证固定比例。
流量在发送前按完整响应正文预扣，传输中途断开不会自动退还未接收部分。上游错误响应如果被转发给客户，也按其最终发送的响应正文大小计量。
压缩与计量调整前已累计的用量不追溯重算。WebSocket 的传输与计量规则不受此次 REST 调整影响。
时间窗口
本服务已取消代理端单次 REST 查询最多两年的时间窗口限制，不再因为单次查询跨度超过两年而返回代理的 HTTP 403。
实际可查询的历史范围取决于接口、股票或期权合约、上游数据覆盖和当前权限。取消时间窗口限制不会扩大上游数据权限或当前 Key 已开通的产品权限。
时间参数按原值转发，包括上游接口支持的 timestamp.gte、`timestamp.gt`、`timestamp.lte`、`timestamp.lt` 等条件组合。
只提供开始或结束条件时，代理不会自动将缺少的条件补成当前时间。实际查询含义以对应上游接口规则为准。
无效时间格式或结束时间早于开始时间，由上游接口校验。代理保留上游返回的状态码和错误内容，不保证所有接口都返回相同错误码。
建议大范围历史查询使用分页，并合理控制 limit，必要时拆分为多个较小时间窗口。请求频率、并发、账期总流量和超时限制仍然生效。
Snapshot 规则
股票全市场 Snapshot          股票单订阅或双订阅支持
股票单标的 Snapshot          股票单订阅或双订阅支持
统一 Snapshot 批量查询       支持已开通的 Stocks / Options 数据
同一请求混合股票和期权       需要双订阅权限
期权链 Snapshot              期权单订阅或双订阅支持分页查询
期权单合约 Snapshot          期权单订阅或双订阅支持

股票全市场 Snapshot 中的最近分钟汇总仅覆盖对应的汇总时段。完整历史分钟线需要使用 K 线接口查询。
指数期权链 Snapshot 示例：
/v3/snapshot/options/I:SPX
/v3/snapshot/options/I:NDX
这些是 Options Snapshot 路径，需要期权单订阅或双订阅权限。独立的 Indices 数据接口不在此权限范围内。
某个标的的期权链 Snapshot 可包含该标的不同到期日、行权价和看涨／看跌合约的当前快照，完整结果可能需要多页查询。
是否包含 Greeks、implied_volatility、underlying_asset 等字段，取决于上游对相应合约和标的返回的数据，不保证每个结果都具备全部字段。
需要注意：
- Snapshot 中的 Greeks 是当前快照数据。该接口不提供任意历史时刻的 Greeks 查询。
- 部分合约可能缺少 Delta、Gamma、Theta、Vega 或 IV。
- open_interest 是上一交易日结束时的持仓量。
- GEX、Gamma Wall 等加工指标需要客户根据原始数据及自己的计算口径生成，本服务不直接提供这些成品指标。
十、WebSocket Python 客户端示例
安装依赖
pip install websockets
示例代码
import asyncio
import websockets

URL = "wss://massive-1.pickalphas.com/ws?key=你的Key"


async def main():
    async with websockets.connect(URL) as ws:
        await ws.send('{"action":"subscribe","params":"T.MU,Q.MU"}')
        while True:
            msg = await ws.recv()
            print(msg)


asyncio.run(main())
上述股票示例适用于股票单订阅或双订阅。美国 2 号客户请将 URL 中的域名换为 <MASSIVE_HOST>。
期权单订阅客户可将订阅消息替换为：
await ws.send(
    '{"action":"subscribe","params":"T.O:SPY261218C00650000,Q.O:SPY261218C00650000"}'
)
请将示例期权代码替换为实际需要且有效的具体合约。
此示例仅演示连接、订阅和读取消息，不包含自动重连。正式使用时，应自行加入重连退避、重新订阅和异常处理。不要在消息接收循环中执行长时间阻塞操作。高频行情建议将读取与后续处理分离，并使用有界队列。
十一、REST Python 客户端示例
安装依赖
pip install requests
以下示例中的 requests 通常会自动协商 gzip 并自动解压，无需手动处理压缩数据。
如需明确指定，可以在 headers 中增加：
"Accept-Encoding": "gzip"
如需未压缩传输，则增加：
"Accept-Encoding": "identity"
以下示例使用美国 1 号域名。美国 2 号客户请将域名替换为 <MASSIVE_HOST>，包括后续分页请求。
请根据已开通的产品权限选择示例。股票单订阅不能执行期权接口示例，期权单订阅不能执行股票接口示例。
批量调用时，请分别控制股票与期权的并发。同一客户在同一服务节点，每类最多同时处理 10 笔 REST 请求。多个进程或设备应一起计算。收到 503 后，请按第十二节的说明等待再重试，并限制重试次数。
REST K 线查询示例
以下股票 K 线示例需要股票单订阅或双订阅权限。
import requests

url = "https://massive-1.pickalphas.com/v2/aggs/ticker/AAPL/range/1/minute/2026-06-01/2026-06-02"
headers = {
    "X-Proxy-Key": "你的Key",
    "Accept-Encoding": "gzip"
}

response = requests.get(url, headers=headers, timeout=30)
print(response.status_code)
print(response.text)
期权 K 线使用具体期权合约代码替换路径中的股票 ticker，并选择适合该合约的查询日期。需要期权单订阅或双订阅权限。
如需全市场股票的完整历史分钟线，应先获取所需股票列表，再按 ticker 分别请求分钟线。
REST 股票单标的 Snapshot 示例
需要股票单订阅或双订阅权限。
import requests

url = "https://massive-1.pickalphas.com/v2/snapshot/locale/us/markets/stocks/tickers/AAPL"
headers = {
    "X-Proxy-Key": "你的Key",
    "Accept-Encoding": "gzip"
}

response = requests.get(url, headers=headers, timeout=30)
print(response.status_code)
print(response.text)

REST 全市场股票 Snapshot 示例
需要股票单订阅或双订阅权限。
import requests

url = "https://massive-1.pickalphas.com/v2/snapshot/locale/us/markets/stocks/tickers"
headers = {
    "X-Proxy-Key": "你的Key",
    "Accept-Encoding": "gzip"
}

response = requests.get(url, headers=headers, timeout=30)
print(response.status_code)
print(response.text)
该接口可以返回全市场股票的当前快照，具体字段取决于上游返回内容。其中最近分钟汇总等字段不代表返回了每只股票的全部历史分钟线。
如果只需要部分股票，可使用该接口支持的 tickers 参数：
params = {"tickers": "AAPL,TSLA,NVDA"}

response = requests.get(
    url,
    headers=headers,
    params=params,
    timeout=30
)
REST 全市场股票日线 Grouped Daily 示例
需要股票单订阅或双订阅权限。
import requests

url = "https://massive-1.pickalphas.com/v2/aggs/grouped/locale/us/market/stocks/2026-10-23"
headers = {
    "X-Proxy-Key": "你的Key",
    "Accept-Encoding": "gzip"
}
params = {"adjusted": "true"}

response = requests.get(
    url,
    headers=headers,
    params=params,
    timeout=30
)

print(response.status_code)
print(response.text)

将路径中的日期替换为需要查询的交易日期。该接口返回指定日期的全市场股票日线汇总。
REST 股票 IPO 查询示例
需要股票单订阅或双订阅权限。
import requests

url = "https://massive-1.pickalphas.com/vX/reference/ipos"
headers = {
    "X-Proxy-Key": "你的Key",
    "Accept-Encoding": "gzip"
}
params = {
    "order": "desc",
    "limit": 10,
    "sort": "listing_date"
}

response = requests.get(
    url,
    headers=headers,
    params=params,
    timeout=30
)

print(response.status_code)
print(response.text)
接口路径为 /vX/reference/ipos，其中 X 为大写，不要替换为 /v3/reference/ipos。
IPO 查询结果可能分页。如果返回 next_url，请按本节“REST 期权链 Snapshot 示例”中的分页方法继续请求，每页分别计入请求次数和流量。
REST 股票标的事件查询示例
需要股票单订阅或双订阅权限。
import requests

url = "https://massive-1.pickalphas.com/vX/reference/tickers/META/events"
headers = {
    "X-Proxy-Key": "你的Key",
    "Accept-Encoding": "gzip"
}

response = requests.get(url, headers=headers, timeout=30)
print(response.status_code)
print(response.text)
将 META 替换为需要查询的股票代码或上游支持的标识符，保留 /vX/ 中的大写 X。
REST 统一 Snapshot 批量查询示例
以下股票批量示例需要股票单订阅或双订阅权限。
import requests

url = "https://massive-1.pickalphas.com/v3/snapshot"
headers = {
    "X-Proxy-Key": "你的Key",
    "Accept-Encoding": "gzip"
}
params = {
    "ticker.any_of": "AAPL,TSLA,NVDA",
    "limit": 10
}

response = requests.get(
    url,
    headers=headers,
    params=params,
    timeout=30
)

print(response.status_code)
print(response.text)
对于精确 ticker 列表，不要额外附加不受上游支持的 type 参数组合。
范围查询示例：
params = {
    "type": "stocks",
    "ticker.gte": "A",
    "ticker.lt": "B",
    "limit": 250
}
同一请求混合股票 ticker 和具体期权合约 ticker 时，需要双订阅权限，并各占一笔股票和期权并发额度。是否支持某个筛选参数或组合，仍以上游接口规则为准。
REST 期权链 Snapshot 示例
需要期权单订阅或双订阅权限。
import requests

url = "https://massive-1.pickalphas.com/v3/snapshot/options/SPY"
headers = {
    "X-Proxy-Key": "你的Key",
    "Accept-Encoding": "gzip"
}
params = {"limit": 250}

response = requests.get(
    url,
    headers=headers,
    params=params,
    timeout=30
)

print(response.status_code)
print(response.text)
如需指数期权链，可使用相应路径，例如：
https://massive-1.pickalphas.com/v3/snapshot/options/I:SPX
期权链结果可能分页。一页结果不一定包含全部合约。后续分页仍应通过首次请求所用的节点域名发送，并在请求头中携带自己的客户 Key。
处理 next_url 时，只取其中的路径和分页参数，去掉上游 Key 参数。不要将客户 Key 发送到 next_url 中的上游域名。
以下代码接在上面的期权链示例之后。它会从首次请求的 url 取出所属节点，因此美国 2 号客户只需改前面的 url：
from urllib.parse import parse_qsl, urlsplit

response.raise_for_status()
data = response.json()
next_url = data.get("next_url")

if next_url:
    node = urlsplit(url)
    parts = urlsplit(next_url)
    next_proxy_url = f"{node.scheme}://{node.netloc}{parts.path}"
    next_params = [
        (key, value)
        for key, value in parse_qsl(
            parts.query,
            keep_blank_values=True
        )
        if key.lower() not in {"apikey", "key"}
    ]

    next_response = requests.get(
        next_proxy_url,
        headers=headers,
        params=next_params,
        timeout=30
    )

    print(next_response.status_code)
    next_response.raise_for_status()
    print(next_response.text)

    如果下一页仍返回 next_url，按相同方式继续分页。每页请求分别计入请求次数和流量。
请在当前页成功返回后再解析 JSON 和推进分页。当前页遇到 503 等暂时性错误时，可按第十二节的说明重试同一页。
REST 期权单合约 Snapshot 示例
需要期权单订阅或双订阅权限。
import requests

url = "https://massive-1.pickalphas.com/v3/snapshot/options/SPY/O:SPY261218C00650000"
headers = {
    "X-Proxy-Key": "你的Key",
    "Accept-Encoding": "gzip"
}

response = requests.get(url, headers=headers, timeout=30)
print(response.status_code)
print(response.text)
示例中的期权合约仅用于说明格式。实际查询应替换为存在且适合查询时间的具体合约。
十二、常见错误说明
401 Unauthorized
REST Key 不正确、已停用、已过期，或者 REST 请求中没有携带 Key。
先核对请求域名是否与「我的数据服务」显示的节点一致，再检查请求头。REST 行情查询使用所属节点的 HTTPS 域名和行情路径。查询授权和用量时，使用同一域名的 /my-license，并携带 X-Proxy-Key 请求头。
400 Bad Request
上游接口可能因请求参数、时间格式或时间范围不正确而返回此错误，例如：
- 时间参数格式不符合该接口要求。
- 结束时间早于开始时间。
- 参数名称或取值不受该接口支持。
- 在不支持通配符的接口中使用 ticker=A* 等写法。
- 在统一 Snapshot 接口中同时传入不兼容的精确 ticker 列表与 type 参数。
具体错误以响应正文为准。代理允许转发批量参数和通配符后，上游仍可能对不支持的写法返回 400。时间格式和起止顺序由上游校验，不同接口对错误时间条件返回的状态码可能不同。
403 Forbidden
可能的原因包括：
- WebSocket Key 无效、已过期或无权连接。
- /my-license 查询使用的 Key 无效、已停用或已经过期。
- 股票单订阅请求期权 REST 接口，或期权单订阅请求股票 REST 接口。
- 期权单订阅请求股票 IPO、股票标的事件等 Stocks 接口。
- 单订阅在同一批次中请求未开通的另一类资产。
- 请求 Flat Files。
- 请求 Stocks 和 Options 之外的资产类别。
- 请求未开放转发的接口。
- 上游权限不足。
请求未开通的资产时，REST 可能返回：
{"detail":"requested data product is not enabled for this key"}
全市场股票 Snapshot、Grouped Daily、批量参数和通配符，不再单独因原来的代理禁止规则返回 403。
IPO 正确路径 /vX/reference/ipos 和股票标的事件正确路径 /vX/reference/tickers/{id}/events 已开放给股票单订阅和双订阅客户。如果仍返回 403，请检查当前 Key 的产品权限、请求路径和响应正文。
本服务不再因单次 REST 查询跨度超过两年而返回代理的 403。上游仍可能根据其自身权限或接口规则拒绝请求。
404 Not Found
请求路径错误，或者上游没有该合约、该接口或对应资源。请核对节点域名以及域名后的完整路径。
例如，IPO 接口应使用 /vX/reference/ipos，不要写成 /v3/reference/ipos。错误的版本路径可能返回 404。
接口返回成功状态但 results 为空，也可能是该标的、合约或时间范围内没有可用数据。
406 Not Acceptable
客户端的 Accept-Encoding 设置同时拒绝 gzip 和未压缩传输，服务器无法返回可接受的格式。
可将该请求头设置为 gzip 或 identity 后重试。
429 Too Many Requests
REST 请求可能因以下原因返回 429：
- 请求频率超过套餐每分钟限制。
- WebSocket 与 REST 合计流量达到当前账期总流量上限。
- 短时间内重复错误鉴权，触发鉴权失败保护。
上游自身限流也可能返回 429，应结合响应内容判断原因。若是请求频率超限，请降低发起频率。若是账期流量用完，请查询 /my-license 确认剩余流量和账期。
当前账期总流量已经用完时，新的 WebSocket 连接也会在握手升级前返回 HTTP 429，不会建立实时行情连接。
三档套餐的 REST 每日流量均不限，不再因原有的每日 5 GiB 或 10 GiB 限额而拒绝请求。
三档 WebSocket 套餐已取消持续事件速率和短时突发池限制，不再因为超过原 events/s 数值而进行套餐级限速丢弃。
取消 REST 每日流量上限、查询时间窗口限制及全市场／批量查询禁止规则后，套餐每分钟请求频率和账期总流量限制仍然生效。
1008 Policy Violation
WebSocket 连接因套餐或服务策略被关闭。常见原因包括：
- 套餐一或套餐二同一个 Key 同时连接多个 WebSocket。
- 套餐三同一个 Key 同时连接超过 2 个 WebSocket。
- Key 在连接期间到期或失效。
- 当前账期总流量达到上限。
- 其他 WebSocket 使用行为触发服务限制。
订阅参数超过套餐上限、使用不支持的全市场订阅，或订阅未开通的资产时，也可能收到包含具体原因的 status: error 返回。
例如，订阅未开通的资产可能返回：
{"status":"error","reason":"subscription product is not enabled for this key"}
一次请求混合允许和禁止的资产时，整条订阅请求会被拒绝。请按当前 Key 的产品权限调整参数后重新订阅。
WebSocket 断线、消息间断或读取失败
可能的原因包括：
- 客户端网络不稳定。
- 客户端未及时读取或处理消息。
- 发送队列积压。
- 写入超时。
- 服务更新或上游连接异常。
- 当前 Key 的产品权限发生变更。
这些情况可能有不同的关闭原因和关闭代码。请检查网络状态和客户端消费速度，并自行实现重连与重新订阅。服务不保证补发断线期间或积压丢弃的行情。
502 Bad Gateway
上游可能直接返回网关错误，或者服务在读取上游响应、处理压缩正文时失败。
可以稍后重试。若持续出现，请联系客服并提供请求路径、发生时间和错误信息。响应头如有 X-Proxy-Request-ID，请一并提供。
503 Service Unavailable
服务暂时繁忙，或请求等待处理超时。同类请求已达到客户并发上限时，后续请求可能需要等待。
如果响应头带有 Retry-After，请按提示等待后再试。建议限制重试次数，连续失败时逐步延长等待时间。批量任务应适当降低同类并发，避免多笔请求同时反复重试。
收到 503 后，这笔请求已经结束。需要再试时，由客户端重新发起请求。
504 Timeout
等待上游响应超时，或整笔 REST 请求超过处理时限。
可以缩小时间窗口、降低单次返回量或稍后重试。客户端自身超时时间较短时，也可能在收到 HTTP 响应前先报告读取超时。
取消两年时间窗口限制，以及开放全市场／批量查询后，大体量查询仍须在处理时限内完成。
十三、注意事项
- WebSocket 使用 wss:// 加密连接，适合接收实时成交、报价和聚合行情。
- REST API 使用 https://，可以查询允许范围内的全市场股票快照、每日市场汇总、单标的历史行情、期权链快照、股票 IPO 信息及股票标的事件。
- 同一个 Key 可以同时用于 WebSocket 实时行情连接和 REST API 查询。
- 客户应使用「我的数据服务」显示的所属节点域名，Key 不跨节点通用。原 IP 客户切换域名时可继续使用原 Key。
- 单订阅是只开通股票或只开通期权，双订阅同时开通股票和期权。
- 套餐一和套餐二限 1 条 WebSocket 连接，单订阅与双订阅的连接数限制相同。
- 套餐三限 2 条 WebSocket 连接，两条连接共享对应单／双订阅的订阅参数和账期总流量。
- 单订阅只能访问已开通的资产。双订阅可以在同一条 WebSocket 连接里同时订阅股票和期权。
- 三档套餐不设置持续事件速率和短时突发池限制。实际带宽、流量额度和消息接收能力仍受服务与客户端条件约束。
- 客户端应及时读取和处理消息。消费过慢或网络持续阻塞时，可能发生队列丢弃或连接关闭。
- 自动重连由客户端实现，建立新连接后需重新订阅。
- A 与 AM 是不同频道，按实际需要分别订阅。
- 热门股票、活跃期权合约、盘前盘后、开盘前后和重大消息期间，事件速度和流量可能明显增加。
- 本服务仅开放 Stocks 和 Options 范围内的数据，不提供独立的 Futures、Indices、Forex、Crypto 等其他资产类别接口。
- REST 已允许全市场股票 Snapshot、Grouped Daily、批量参数及通配符转发。对应参数是否有效仍取决于上游接口支持。
- 股票 IPO 接口路径为 /vX/reference/ipos，股票标的事件接口路径为 /vX/reference/tickers/{id}/events。两条路径中的 X 均为大写，均需要股票单订阅或双订阅权限。
- REST 的开放不改变 WebSocket 的连接数、订阅参数数量和全市场订阅限制。
- 全市场日线汇总按日期查询。完整历史分钟线仍需要按具体 ticker 查询并自行汇总。
- 某个标的的整条期权链可以分页查询，每页分别计入请求次数和流量。
- Snapshot Greeks 是当前快照数据，部分合约可能缺失。OI 为上一交易日结束时的持仓量，GEX 等加工指标需要自行计算。
- REST 不设置代理端单次查询时间跨度上限，但实际历史范围仍受上游数据覆盖和权限影响。
- 大范围历史查询建议使用分页、合理控制 limit，必要时拆分为较小时间窗口。
- 时间参数按原值转发，无效时间格式和反向时间范围由上游校验。
- 股票和期权 REST 并发分别计算，同一客户在同一服务节点每类最多同时处理 10 笔。套餐每分钟请求上限同时适用。
- 批量任务应控制并发和重试次数。遇到 503 时，如响应头有 Retry-After，请按提示等待后再试。
- REST 每日流量不限。日用量仍按北京时间自然日记录，每日 00:00 切换统计日期不会重置账期总流量。
- REST 支持 gzip 压缩传输，按响应正文大小计量，客户端本地解压不会额外扣量。
- 全市场或批量响应可能较大，频繁重复拉取会更快消耗当前账期额度。
- 查询套餐、产品权限、到期时间和当前账期用量时，请访问所属节点 HTTPS 域名下的 /my-license，并在请求头中携带 X-Proxy-Key。
- WebSocket 和 REST API 流量共同计入当前 30 天账期总流量。
- 双订阅的股票与期权共同使用同一个 Key 的流量池。
- 30 天账期按授权周期计算。提前续费不会立即重置尚未结束的账期额度。
- 历史数据覆盖范围、字段完整性和行情更新频率取决于上游数据及权限。
- Flat Files 下载服务仍不开放。如需历史行情文件或其他定制数据服务，请联系客服单独确认。