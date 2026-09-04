# 仓库审计报告 — 训练功能 MVP 技术基线

> 审计日期：2026-07-09
> 基准分支：develope
> 审计范围：项目根目录、miniprogram/、cloudfunctions/

---

## 1. 技术栈

| 层级 | 技术 |
|------|------|
| 运行平台 | 微信小程序原生 |
| 基础库版本 | 3.16.0 |
| 云开发 | wx.cloud（env: `cloud1-5gpu3nmc673b62c2`） |
| 云数据库 | 微信云开发 MongoDB 文档数据库 |
| 云函数 | Node.js（wx-server-sdk） |
| UI 框架 | 无第三方，纯 WXML/WXSS |
| 状态管理 | 无第三方，Page.data + app.globalData |

---

## 2. 目录结构

```
BYTESYNC/
├── project.config.json          # 小程序项目配置
├── project.private.config.json  # 私有配置（appid 等）
├── cloudfunctions/
│   ├── getOpenId/               # 获取用户 openid
│   └── analyzeMeal/             # AI 图像/文字识别食物
└── miniprogram/
    ├── app.js                   # 全局初始化、globalData
    ├── app.json                 # 页面注册、tabBar、window
    ├── app.wxss                 # 引入全局样式
    ├── sitemap.json
    ├── assets/
    │   ├── icons/               # tabBar 图标等
    │   └── images/              # 静态图片
    ├── components/
    │   ├── camera-button/       # 拍照按钮
    │   ├── date-switcher/       # 日期切换
    │   ├── food-card/           # 食物卡片
    │   ├── food-list-item/      # 食物列表项
    │   ├── macro-bar/           # 宏量进度条
    │   └── summary-card/        # 摘要卡片
    ├── pages/
    │   ├── record/              # 记录页（拍照、手动输入、AI 识别）
    │   ├── summary/             # 今日摘要（双人卡路里汇总）
    │   └── pairing/             # 配对流程页
    ├── styles/
    │   ├── variables.wxss       # 设计 Token（颜色、字号、间距、圆角）
    │   └── common.wxss          # 通用样式（.card, .primary-btn 等）
    └── utils/
        ├── api.js               # 数据库 & 云函数封装
        ├── config.js            # 云环境 ID、默认目标
        ├── formatter.js         # 日期/数字格式化
        ├── nutrition.js         # 未使用（空/保留）
        └── time.js              # getCurrentDate/Time
```

---

## 3. 页面结构与导航

### 3.1 页面注册（app.json → pages）

| 序号 | 路径 | 用途 |
|------|------|------|
| 1 | `pages/record/record` | 拍照记录、AI 识别、手动输入 |
| 2 | `pages/summary/summary` | 今日双人摘要 |
| 3 | `pages/pairing/pairing` | 创建/加入配对 |

### 3.2 tabBar

```json
"tabBar": {
  "list": [
    { "pagePath": "pages/record/record", "text": "记录" },
    { "pagePath": "pages/summary/summary", "text": "今日" }
  ]
}
```

- 当前 **2 个 tab**
- 训练功能需要新增第 3 个 tab：`pages/training/training`，放在中间或最后

### 3.3 页面跳转模式

| 场景 | 方式 | 调用 |
|------|------|------|
| tab 间切换 | switchTab | `wx.switchTab({ url })` |
| 未配对跳转 pairing | redirectTo | `wx.redirectTo({ url })` |
| 配对成功进 summary | switchTab | `wx.switchTab({ url })` |

---

## 4. App 初始化过程

### 4.1 关键代码（app.js）

```js
App({
  globalData: {
    openid:      '',
    userProfile: null,   // { openid, role, userName, pairId }
    pairId:      '',
  },
  onLaunch() {
    wx.cloud.init({ env: config.cloudEnvId, traceUser: true })
    this._initPromise = getOpenId()
      .then(res => { this.globalData.openid = res.openid; return getUserByOpenId(res.openid) })
      .then(res => {
        if (res.data && res.data.length > 0) {
          const profile = res.data[0]
          this.globalData.userProfile = profile
          this.globalData.pairId = profile.pairId || ''
        }
      })
      .catch(err => { console.error('[BiteSync] 初始化失败', err) })
  },
})
```

### 4.2 _initPromise 模式

- `app._initPromise` 是一个 Promise，页面在 `onShow` 或 `onLoad` 中通过 `app._initPromise.then(() => { ... })` 等待初始化完成。
- 这是**异步守卫模式**，训练页面必须沿用。

---

## 5. 用户身份结构

### 5.1 关键字段

| 字段 | 来源 | 用途 |
|------|------|------|
| `openid` | `getOpenId` 云函数 | 用户唯一标识 |
| `userProfile` | `users` 集合 | 用户信息对象 |
| `userProfile.role` | users | `'me'` 或 `'ta'`（配对视角） |
| `userProfile.userName` | users | `'我'` 或 `'Ta'` |
| `userProfile.pairId` | users | 配对 ID |
| `pairId` | globalData | 当前配对 ID |

### 5.2 数据权限影响

- 饮食数据（meals）按 `pairId` 隔离，双方可见
- 训练数据 MVP **按 openid 隔离**（推荐），不共享

---

## 6. 当前数据库集合

| 集合名 | 用途 | 关键字段 |
|--------|------|----------|
| `meals` | 饮食记录 | `pairId, userId, userName, date, calories, ...` |
| `users` | 用户信息 | `openid, role, userName, pairId, goals, createdAt` |
| `pairs` | 配对关系 | `pairId, inviteCode, members[], createdBy, createdAt` |

---

## 7. 当前 API 封装方式（utils/api.js）

### 7.1 设计风格

- **直接调用云数据库**：`wx.cloud.database().collection().where().get()`
- **Promise 返回**：所有方法返回 Promise
- **无中间层**：不使用 Redux/Vuex/MobX
- **云函数**：`wx.cloud.callFunction({ name, data })`

### 7.2 现有函数

```js
// meals
addMeal, addMeals, getMealsByDate, updateMeal, deleteMeal

// users
getUserByOpenId, getUsersByPairId, createUser, updateUserPair, updateUserGoals

// pairs
createPair, getPairByInviteCode, getPairByPairId, joinPair

// cloud
getOpenId, analyzeMeal, analyzeMealByText, deleteCloudFile, callCloudFunction
```

### 7.3 训练功能扩展建议

- 继续在 `utils/api.js` 中追加训练相关函数
- 或新建 `utils/training-api.js`（如函数过多，避免单文件膨胀）
- **不引入新状态管理库**

---

## 8. 页面守卫与加载模式

### 8.1 守卫模式（summary.js）

```js
onShow() {
  app._initPromise.then(() => {
    if (!app.globalData.pairId) {
      wx.redirectTo({ url: '/pages/pairing/pairing' })
      return
    }
    this._loadData(this.data.currentDate)
  })
}
```

### 8.2 训练页面守卫建议

```js
onShow() {
  app._initPromise.then(() => {
    const { openid } = app.globalData
    if (!openid) {
      wx.showToast({ title: '初始化中', icon: 'none' })
      return
    }
    this._loadTrainingData()
  })
}
```

- 训练功能**不强制依赖 pairId**，只需 openid
- 未配对用户也可以使用训练功能（决策：独立于配对）

---

## 9. 可复用资源

### 9.1 设计 Token（styles/variables.wxss）

| Token | 值 | 用途 |
|-------|-----|------|
| `--color-primary` | `#6FCF97` | 主色（柔和绿） |
| `--color-me` | `#4A90E2` | 我（蓝） |
| `--color-ta` | `#F299A1` | Ta（玫瑰） |
| `--color-success` | `#27AE60` | 成功 |
| `--color-warning` | `#EB5757` | 警告/删除 |
| `--font-size-md` | `32rpx` | 正文 |
| `--spacing-lg` | `36rpx` | 大间距 |
| `--radius-lg` | `28rpx` | 卡片圆角 |
| `--shadow-card` | `0 4rpx 20rpx rgba(0,0,0,0.05)` | 卡片阴影 |

### 9.2 通用样式（styles/common.wxss）

| 类名 | 用途 |
|------|------|
| `.card` | 白色圆角卡片 |
| `.primary-btn` | 主按钮（绿色胶囊） |
| `.kcal-number` | 大号热量数字 |
| `.safe-bottom` | 底部安全区 |
| `.section-title` | 分区标题 |
| `.text-primary/.text-accent/.text-warning` | 文字颜色 |

### 9.3 可复用组件

| 组件 | 可否用于训练 | 说明 |
|------|--------------|------|
| `date-switcher` | ✅ | 周切换（改为周一~周日模式） |
| `macro-bar` | ❌ | 营养素进度条，不适用 |
| `food-card` | ❌ | 食物卡片，不适用 |
| `food-list-item` | 参考 | 列表项样式可参考 |

### 9.4 可复用工具函数

| 函数 | 来源 | 用途 |
|------|------|------|
| `formatDate` | formatter.js | `Date` → `YYYY-MM-DD` |
| `formatDateCN` | formatter.js | `YYYY-MM-DD` → `5月19日 周一` |
| `getCurrentDate` | time.js | 当前日期 |
| `getCurrentTime` | time.js | 当前时间 |

---

## 10. 训练功能建议目录

```
miniprogram/
├── pages/
│   └── training/              # 训练首页（周计划打卡）
│       ├── training.js
│       ├── training.json
│       ├── training.wxml
│       └── training.wxss
├── pages/
│   └── training-template/     # 模板编辑页
│       └── ...
├── pages/
│   └── training-history/      # 历史周列表（可选，MVP 可在首页内实现）
│       └── ...
├── components/
│   └── exercise-item/         # 训练项目打卡组件（复用列表样式）
│       └── ...
├── utils/
│   └── training-api.js        # 训练 API（或合并到 api.js）
└── assets/icons/
    ├── training.png           # tabBar 图标
    └── training-active.png
```

---

## 11. 技术债务与风险

### 11.1 现有债务

| 风险 | 严重度 | 影响 | 建议 |
|------|--------|------|------|
| config.js 硬编码 demo 值 | 低 | 已有动态 openid，但 demo_pair/demo_user 仍存在 | 可忽略，实际不使用 |
| nutrition.js 空文件 | 无 | 未使用 | 可删除或忽略 |
| 无自动化测试 | 中 | 无法回归验证 | 训练功能手动验收 |
| 无分包 | 低 | 当前包体小，暂无影响 | 训练资源膨胀后考虑分包 |

### 11.2 训练功能引入风险

| 风险 | 缓解措施 |
|------|----------|
| tabBar 需改 app.json | 第一个实施阶段完成 |
| 新集合权限配置 | 云控制台手动配置 |
| 视频外链微信限制 | 使用 `wx.setClipboardData` + `web-view` 白名单降级 |
| 打卡并发写入 | 使用 `db.command.inc(1)` 原子自增 |

---

## 12. 审计结论

1. **技术栈稳定**：原生 + 云开发，无第三方依赖，训练功能可无缝集成
2. **初始化模式清晰**：`_initPromise` 异步守卫可直接复用
3. **数据库直连**：API 风格简洁，训练 API 沿用即可
4. **样式系统完善**：Design Token + 通用类，训练 UI 复用
5. **组件复用有限**：需新建 `exercise-item` 等训练专用组件
6. **包体积可控**：当前无大型依赖，训练功能不引入新框架
7. **tabBar 需扩展**：从 2 项扩展到 3 项，需修改 `app.json`

---

*本文档为只读审计报告，不修改任何运行代码。*
