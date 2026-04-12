# 每日文章编写需求

> 根据爬取数据以及xmeta相关在线接口，生成微信的每日文章

## 微信文章封面生成




## 今日发售日历

#### 发售日历
1.  根据LaunchCalendar表中爬取的xmeta发售日历数据，获取当日的发售数据同时需要将日历关联的藏品，使用h5/goods/archiveGoods接口，请求藏品在二级市场预售信息，total为已预售总量，goodsMinPrice为当前最低价格。


2.  确认今日发售的集合和对应该的藏品生成图片/Users/abbott/Documents/GitHub/xmeta_claw/backend/app/article/charts/cards.py


3. 需要根据藏品名从JingtanSkuHomepageDetail中获取发生藏品的author和owner, sku_desc等重要信息， author为鲸探方的IP方，owner为鲸探平台IP的发行主体公司， sku_desc为藏品描描述。

4. 根据以上信息目前可以直接使用/Users/abbott/Documents/GitHub/xmeta_claw/backend/app/article/charts/cover.py 生成微信文章封面。生成的封面路径需要保存到Article表，后台需要展示，并简约描述今日发售情况。

#### 藏品分析解读
* 对每个藏品稍作详细一点的分析，主要结合藏品 sku_desc、发倍数量、预售总量，goodsMinPrice等分析 ，如果藏品为文物字画版块可以结合藏品背景分析一下。

#### IP分析和发行商分析

1. 若从发售日历中有IP，则查询IP上次发行的时间和上次日历发行数据。并根据IP在MarketIPSnapshot表中上查询昨天市场值和交易量等信息。

2. 则通过JingtanSkuHomepageDetail表查询，发商行是否有其它IP，可以取出最好的发行时间和藏品。

3. 没有IP信息的主要对发行商主体进行分析。

根据提取的信息生成IP总结。



## 昨天行情分析

### 市值和交易量分析
对近7天的市值和交易量进行分析。创建创建line图表。

### 板块析分
对近7天的版本交易进行分析，创建适合的图表。

### 热门藏品分析

根据昨天热门藏品，取top10进行分析，并生成合适的图表。

### 热门IP分析

根据昨天IP成交易量进行分析。可以取出最近7天每个IP的市场和成交量，并生成合适的表图。


进行适当的总结








