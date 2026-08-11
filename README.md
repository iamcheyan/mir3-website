# 传奇3 · 资料站镜像

17173 传奇3 资料站(`mir3.17173.com`)的静态镜像,部署于 GitHub Pages:

- 线上地址:https://mir3.iamcheyan.com
- 源仓库:https://github.com/iamcheyan/mir3-website
- 数据与图片版权归 17173.com 所有,仅供个人研究使用

## 内容清单

| 分类 | 页面 | 说明 |
|------|------|------|
| `mob/` | 21 页 | 怪物图鉴(一般怪物 ~ 真天黑度) |
| `item/` | 12 页 | 物品资料(item1 ~ item12 分页) |
| `skill/` | 3 页 | 技能资料(skill.htm + 2/3) |
| `mission/` | 4 页 | 任务资料(mission + mission1/2 + wan) |
| `map/` | 2 页 | 地图资料(map + sj) |
| `images/` | 582 张 | 全部本地化图片(mob/item/skill/mission/map/up/class/images) |

首页 `index.html` 提供全部分类入口。站内分页互链(如 item1~12、skill/2/3、mission1/2/wan)保持原站结构。

## 镜像方法

源站结构:HTML 页面在 `mir3.17173.com`(curl 直接可下,200);图片/CSS 在 `i.17173cdn.com`,被腾讯 EdgeOne 反爬拦截(curl 一律 HTTP 567 JS 验证)。

### 抓取 HTML

```bash
wget --mirror --no-parent --page-requisites --convert-links \
  --span-hosts --domains=mir3.17173.com,i.17173cdn.com \
  --exclude-domains=log.17173.com,js.17173.com,ue.17173cdn.com \
  -e robots=off -w 1 --timeout=20 --tries=3 -P <dest> <url>
```

### 抓取 CDN 图片(必须过 EdgeOne)

1. 浏览器打开任意源页面(如 `https://mir3.17173.com/item/item1.htm`),页面内图片全部加载即验证通过。
2. 取 cookie:`page.cookies()` 拼 `name=value; ...`。
3. Node 侧 fetch,带 `Cookie` + `Referer`(源页面 URL)+ Chrome `User-Agent`。
4. 落盘路径规则:URL `https://i.17173cdn.com/z6mhfw/mir3/<rest>` → 仓库 `images/<rest>`。

### 反爬避坑(实测)

- **请求速率**:连续快速请求会返回假图 —— EdgeOne 降级为一个 17660 字节的占位 GIF(魔数是合法 GIF 头,内容同尺寸 800×600 占位)。**间隔 ≥3s** 可避免。
- **Accept 头**:`Accept: image/jpeg,image/gif,image/*` 拿真 JPG/GIF;带 `image/webp` 时 jpg 会被转成 WebP 返回。
- **校验**:落盘前检查魔数(`GIF8` / `FFD8FF`)**且 size ≠ 17660**,否则重试。
- **IP 级限流**:触发后所有 CDN 请求一段窗口内全失败,需开**全新浏览器 tab**(重新过验证)或等待冷却。

### 链接重写

页面入仓后重写图片引用(两种形式都要处理):

```bash
sed -i 's|//i\.17173cdn\.com/z6mhfw/mir3/images/|../images/|g; s|https://i\.17173cdn\.com/z6mhfw/mir3/images/|../images/|g' <page>
```

站内导航保留绝对路径 `/mob/mob1.htm`、`/item/item1.htm`(Pages 域根 = 仓库根)。

## 已知限制

- 各页顶部 `ue.17173cdn.com` 栏(CSS/JS/装饰图)未本地化,在线可能被 567 拦截,不影响正文(内容表格为内联样式)。
- 站内导航指向未镜像栏目(`guide/`、`jinyan/`、`jiaoliu/` 等)的链接会 404;如需要可单独抓取对应页面入仓,无需改动现有页面。
- 原站 `images/images/main.css`(skill 页引用)被 EdgeOne 特别保护且纯装饰,已从 skill 3 页移除引用。

## 部署

推送 `main` 分支即触发 Pages 构建(CNAME 文件自动绑定 `mir3.iamcheyan.com`):

```bash
git add -A && git commit -m "..." && git push origin main
```

与个人站 `iamcheyan.github.io`(`iamcheyan.com`)互不干扰,GitHub 按 Host 路由。
