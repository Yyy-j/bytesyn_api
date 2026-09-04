# 训练功能 MVP — 数据模型、API 合约与验收测试

> 版本：1.0
> 日期：2026-07-09
> 状态：已确定

---

## 目录

- [1. 云数据库集合设计](#1-云数据库集合设计)
- [2. API 函数合约](#2-api-函数合约)
- [3. 验收测试矩阵](#3-验收测试矩阵)
- [4. 后续实施阶段](#4-后续实施阶段)

---

## 1. 云数据库集合设计

### 1.1 集合概览

| 集合名 | 用途 | 数据权限 |
|--------|------|----------|
| `trainingTemplates` | 用户的每周训练模板 | 仅创建者可读写 |
| `trainingWeeks` | 周计划快照（含打卡进度） | 仅创建者可读写 |
| `trainingExercises` | 用户自定义动作库 | 仅创建者可读写 |

> 固定动作库不存数据库，硬编码在前端 `utils/training-exercises.js` 中，减少云调用。

---

### 1.2 trainingTemplates（训练模板）

#### 用途

存储用户创建的每周训练计划模板。每个用户最多 1 个模板（MVP）。

#### 字段定义

| 字段名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| `_id` | string | 是 | 自动 | 文档 ID |
| `openid` | string | 是 | - | 所有者 openid |
| `version` | number | 是 | 1 | 模板版本号，每次修改 +1 |
| `days` | array[7] | 是 | - | 周一到周日的训练安排 |
| `days[n].dayIndex` | number | 是 | - | 0=周一, 6=周日 |
| `days[n].exercises` | array | 是 | [] | 当日训练项目列表 |
| `days[n].exercises[m]` | object | 是 | - | 单个训练项目 |
| `.exerciseId` | string | 是 | - | 动作 ID（固定库或自定义） |
| `.exerciseName` | string | 是 | - | 动作名称（快照） |
| `.category` | string | 否 | '' | 分类（胸/背/腿/肩/手臂/核心） |
| `.targetSets` | number | 是 | 3 | 目标组数 |
| `.targetReps` | number | 是 | 12 | 每组目标次数 |
| `.targetWeight` | number | 否 | 0 | 目标重量（kg），0 表示自重 |
| `.videoLinks` | array | 否 | [] | 教学视频链接（最多 3 条） |
| `.videoLinks[k].url` | string | 是 | - | 视频链接 |
| `.videoLinks[k].title` | string | 否 | '' | 视频标题 |
| `.order` | number | 是 | - | 排序序号 |
| `createdAt` | Date | 是 | - | 创建时间 |
| `updatedAt` | Date | 是 | - | 最后更新时间 |

#### 示例 JSON

```json
{
  "_id": "tpl_abc123",
  "openid": "oXXXX",
  "version": 3,
  "days": [
    {
      "dayIndex": 0,
      "exercises": [
        {
          "exerciseId": "ex_squat",
          "exerciseName": "深蹲",
          "category": "腿",
          "targetSets": 3,
          "targetReps": 12,
          "targetWeight": 60,
          "videoLinks": [
            { "url": "https://example.com/squat-tutorial", "title": "深蹲教程" }
          ],
          "order": 0
        },
        {
          "exerciseId": "ex_leg_press",
          "exerciseName": "腿举",
          "category": "腿",
          "targetSets": 4,
          "targetReps": 10,
          "targetWeight": 80,
          "videoLinks": [],
          "order": 1
        }
      ]
    },
    { "dayIndex": 1, "exercises": [] },
    { "dayIndex": 2, "exercises": [/* ... */] },
    { "dayIndex": 3, "exercises": [] },
    { "dayIndex": 4, "exercises": [/* ... */] },
    { "dayIndex": 5, "exercises": [] },
    { "dayIndex": 6, "exercises": [] }
  ],
  "createdAt": "2026-07-01T10:00:00Z",
  "updatedAt": "2026-07-09T08:30:00Z"
}
```

#### 索引建议

| 索引字段 | 类型 | 用途 |
|----------|------|------|
| `openid` | 唯一 | 每用户一个模板，快速查询 |

#### 权限

- `read`: 仅创建者
- `write`: 仅创建者

#### 删除策略

- 用户删除模板 → 软删除（设 `deletedAt`）或直接删除
- 关联的周计划快照保留（历史不变）

---

### 1.3 trainingWeeks（周计划快照）

#### 用途

存储每周训练计划的快照，包含打卡进度。生成后与模板解耦。

#### 字段定义

| 字段名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| `_id` | string | 是 | 自动 | 文档 ID |
| `openid` | string | 是 | - | 所有者 openid |
| `weekId` | string | 是 | - | 周标识，格式 `YYYY-Www`（如 `2026-W28`） |
| `weekStart` | string | 是 | - | 周一日期 `YYYY-MM-DD` |
| `weekEnd` | string | 是 | - | 周日日期 `YYYY-MM-DD` |
| `templateVersion` | number | 是 | - | 生成时的模板版本 |
| `snapshotAt` | Date | 是 | - | 快照生成时间 |
| `days` | array[7] | 是 | - | 周一到周日的训练安排（深拷贝） |
| `days[n].dayIndex` | number | 是 | - | 0=周一, 6=周日 |
| `days[n].date` | string | 是 | - | 当日日期 `YYYY-MM-DD` |
| `days[n].exercises` | array | 是 | [] | 当日训练项目 |
| `.exerciseId` | string | 是 | - | 动作 ID |
| `.exerciseName` | string | 是 | - | 动作名称（快照） |
| `.category` | string | 否 | '' | 分类 |
| `.targetSets` | number | 是 | - | 目标组数 |
| `.targetReps` | number | 是 | - | 每组目标次数 |
| `.targetWeight` | number | 否 | 0 | 目标重量 |
| `.videoLinks` | array | 否 | [] | 视频链接（快照） |
| `.order` | number | 是 | - | 排序 |
| `.completedSets` | number | 是 | 0 | 已完成组数 |
| `.setDetails` | array | 否 | [] | 每组详情 |
| `.setDetails[k].weight` | number | 是 | - | 实际重量 |
| `.setDetails[k].reps` | number | 否 | - | 实际次数（可选） |
| `.setDetails[k].rpe` | number | 否 | null | RPE 1-10（可选） |
| `.setDetails[k].note` | string | 否 | '' | 备注（可选） |
| `.setDetails[k].completedAt` | Date | 是 | - | 完成时间 |
| `createdAt` | Date | 是 | - | 创建时间 |
| `updatedAt` | Date | 是 | - | 最后更新时间 |

#### 示例 JSON

```json
{
  "_id": "week_xyz789",
  "openid": "oXXXX",
  "weekId": "2026-W28",
  "weekStart": "2026-07-06",
  "weekEnd": "2026-07-12",
  "templateVersion": 3,
  "snapshotAt": "2026-07-06T08:00:00Z",
  "days": [
    {
      "dayIndex": 0,
      "date": "2026-07-06",
      "exercises": [
        {
          "exerciseId": "ex_squat",
          "exerciseName": "深蹲",
          "category": "腿",
          "targetSets": 3,
          "targetReps": 12,
          "targetWeight": 60,
          "videoLinks": [
            { "url": "https://example.com/squat-tutorial", "title": "深蹲教程" }
          ],
          "order": 0,
          "completedSets": 2,
          "setDetails": [
            { "weight": 60, "reps": 12, "rpe": 7, "note": "", "completedAt": "2026-07-06T10:30:00Z" },
            { "weight": 62.5, "reps": 10, "rpe": 8, "note": "稍重", "completedAt": "2026-07-06T10:35:00Z" }
          ]
        }
      ]
    },
    { "dayIndex": 1, "date": "2026-07-07", "exercises": [] }
    /* ... 其他日期 */
  ],
  "createdAt": "2026-07-06T08:00:00Z",
  "updatedAt": "2026-07-06T10:35:00Z"
}
```

#### 索引建议

| 索引字段 | 类型 | 用途 |
|----------|------|------|
| `{ openid: 1, weekId: 1 }` | 复合唯一 | 防止重复生成，快速查询 |
| `{ openid: 1, weekStart: -1 }` | 复合 | 历史周列表按时间倒序 |

#### 权限

- `read`: 仅创建者
- `write`: 仅创建者

#### 历史快照策略

- **不允许删除**：历史周计划永久保留
- **不允许结构修改**：只允许更新 `completedSets`、`setDetails`、`updatedAt`
- **快照隔离**：模板修改不影响已生成的周计划

---

### 1.4 trainingExercises（自定义动作）

#### 用途

存储用户创建的自定义训练动作。

#### 字段定义

| 字段名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| `_id` | string | 是 | 自动 | 文档 ID，同时作为 exerciseId |
| `openid` | string | 是 | - | 所有者 openid |
| `name` | string | 是 | - | 动作名称（最长 20 字符） |
| `category` | string | 否 | '其他' | 分类 |
| `defaultSets` | number | 否 | 3 | 默认组数 |
| `defaultReps` | number | 否 | 12 | 默认次数 |
| `defaultWeight` | number | 否 | 0 | 默认重量 |
| `videoLinks` | array | 否 | [] | 教学视频（最多 3 条） |
| `isDeleted` | boolean | 否 | false | 软删除标记 |
| `createdAt` | Date | 是 | - | 创建时间 |
| `updatedAt` | Date | 是 | - | 更新时间 |

#### 示例 JSON

```json
{
  "_id": "custom_ex_001",
  "openid": "oXXXX",
  "name": "哑铃飞鸟",
  "category": "胸",
  "defaultSets": 3,
  "defaultReps": 15,
  "defaultWeight": 10,
  "videoLinks": [
    { "url": "https://example.com/fly", "title": "哑铃飞鸟教程" }
  ],
  "isDeleted": false,
  "createdAt": "2026-07-05T10:00:00Z",
  "updatedAt": "2026-07-05T10:00:00Z"
}
```

#### 索引建议

| 索引字段 | 类型 | 用途 |
|----------|------|------|
| `{ openid: 1, isDeleted: 1 }` | 复合 | 查询用户未删除的动作 |

#### 权限

- `read`: 仅创建者
- `write`: 仅创建者

#### 删除策略

- **软删除**：设置 `isDeleted: true`
- **被引用保护**：模板/周计划中引用的动作，快照已保存名称，删除不影响历史

---

### 1.5 固定动作库（前端硬编码）

不存数据库，在 `utils/training-exercises.js` 中硬编码：

```js
// utils/training-exercises.js
module.exports = {
  categories: ['胸', '背', '腿', '肩', '手臂', '核心'],
  exercises: [
    // 胸
    { id: 'ex_bench_press', name: '杠铃卧推', category: '胸', defaultSets: 4, defaultReps: 8, videoLinks: [] },
    { id: 'ex_incline_press', name: '上斜卧推', category: '胸', defaultSets: 3, defaultReps: 10, videoLinks: [] },
    { id: 'ex_dumbbell_fly', name: '哑铃飞鸟', category: '胸', defaultSets: 3, defaultReps: 12, videoLinks: [] },
    // 背
    { id: 'ex_pull_up', name: '引体向上', category: '背', defaultSets: 3, defaultReps: 8, videoLinks: [] },
    { id: 'ex_lat_pulldown', name: '高位下拉', category: '背', defaultSets: 3, defaultReps: 12, videoLinks: [] },
    { id: 'ex_barbell_row', name: '杠铃划船', category: '背', defaultSets: 4, defaultReps: 10, videoLinks: [] },
    // 腿
    { id: 'ex_squat', name: '深蹲', category: '腿', defaultSets: 4, defaultReps: 8, videoLinks: [] },
    { id: 'ex_leg_press', name: '腿举', category: '腿', defaultSets: 4, defaultReps: 12, videoLinks: [] },
    { id: 'ex_leg_curl', name: '腿弯举', category: '腿', defaultSets: 3, defaultReps: 12, videoLinks: [] },
    { id: 'ex_calf_raise', name: '提踵', category: '腿', defaultSets: 4, defaultReps: 15, videoLinks: [] },
    // 肩
    { id: 'ex_overhead_press', name: '肩推', category: '肩', defaultSets: 4, defaultReps: 10, videoLinks: [] },
    { id: 'ex_lateral_raise', name: '侧平举', category: '肩', defaultSets: 3, defaultReps: 15, videoLinks: [] },
    { id: 'ex_face_pull', name: '面拉', category: '肩', defaultSets: 3, defaultReps: 15, videoLinks: [] },
    // 手臂
    { id: 'ex_bicep_curl', name: '二头弯举', category: '手臂', defaultSets: 3, defaultReps: 12, videoLinks: [] },
    { id: 'ex_tricep_pushdown', name: '三头下压', category: '手臂', defaultSets: 3, defaultReps: 12, videoLinks: [] },
    // 核心
    { id: 'ex_plank', name: '平板支撑', category: '核心', defaultSets: 3, defaultReps: 60, videoLinks: [] },
    { id: 'ex_crunch', name: '卷腹', category: '核心', defaultSets: 3, defaultReps: 20, videoLinks: [] },
  ],
}
```

---

## 2. API 函数合约

### 2.1 沿用现有 api.js 风格

```js
const funcName = (params) => {
  const db = wx.cloud.database()
  return db.collection('xxx').where({ ... }).get()  // 返回 Promise
}
```

### 2.2 训练模板 API

#### getTrainingTemplate

| 项目 | 内容 |
|------|------|
| **函数名** | `getTrainingTemplate` |
| **输入** | `openid: string` |
| **返回** | `Promise<{ data: Template[] }>` |
| **失败** | 网络错误、权限错误 |
| **调用方式** | 直接数据库 |
| **云函数** | 否 |

```js
const getTrainingTemplate = (openid) => {
  const db = wx.cloud.database()
  return db.collection('trainingTemplates').where({ openid }).limit(1).get()
}
```

#### createTrainingTemplate

| 项目 | 内容 |
|------|------|
| **函数名** | `createTrainingTemplate` |
| **输入** | `{ openid, days }` |
| **返回** | `Promise<{ _id }>` |
| **失败** | 重复创建、字段缺失 |
| **调用方式** | 直接数据库 |

```js
const createTrainingTemplate = ({ openid, days }) => {
  const db = wx.cloud.database()
  const now = new Date()
  return db.collection('trainingTemplates').add({
    data: { openid, version: 1, days, createdAt: now, updatedAt: now }
  })
}
```

#### updateTrainingTemplate

| 项目 | 内容 |
|------|------|
| **函数名** | `updateTrainingTemplate` |
| **输入** | `{ openid, days }` |
| **返回** | `Promise<{ stats: { updated } }>` |
| **原子更新** | `version` 使用 `db.command.inc(1)` |

```js
const updateTrainingTemplate = ({ openid, days }) => {
  const db = wx.cloud.database()
  const _ = db.command
  return db.collection('trainingTemplates').where({ openid }).update({
    data: { days, version: _.inc(1), updatedAt: new Date() }
  })
}
```

---

### 2.3 周计划 API

#### getOrCreateTrainingWeek

| 项目 | 内容 |
|------|------|
| **函数名** | `getOrCreateTrainingWeek` |
| **输入** | `{ openid, weekId }` |
| **返回** | `Promise<{ data: Week, created: boolean }>` |
| **幂等** | 已存在则直接返回，不重复创建 |
| **调用方式** | 直接数据库 |

```js
const getOrCreateTrainingWeek = async ({ openid, weekId }) => {
  const db = wx.cloud.database()
  
  // 1. 查询是否已存在
  const existing = await db.collection('trainingWeeks')
    .where({ openid, weekId }).limit(1).get()
  if (existing.data.length > 0) {
    return { data: existing.data[0], created: false }
  }
  
  // 2. 查询模板
  const tplRes = await db.collection('trainingTemplates')
    .where({ openid }).limit(1).get()
  if (tplRes.data.length === 0) {
    return { data: null, created: false }  // 无模板
  }
  
  // 3. 生成周计划
  const template = tplRes.data[0]
  const weekDates = getWeekDates(weekId)  // 返回周一到周日的日期数组
  const now = new Date()
  const weekData = {
    openid,
    weekId,
    weekStart: weekDates[0],
    weekEnd: weekDates[6],
    templateVersion: template.version,
    snapshotAt: now,
    days: template.days.map((day, i) => ({
      ...day,
      date: weekDates[i],
      exercises: day.exercises.map(ex => ({
        ...ex,
        completedSets: 0,
        setDetails: []
      }))
    })),
    createdAt: now,
    updatedAt: now
  }
  
  // 4. 写入
  const addRes = await db.collection('trainingWeeks').add({ data: weekData })
  weekData._id = addRes._id
  return { data: weekData, created: true }
}
```

#### getTrainingWeekHistory

| 项目 | 内容 |
|------|------|
| **函数名** | `getTrainingWeekHistory` |
| **输入** | `{ openid, limit = 10, skip = 0 }` |
| **返回** | `Promise<{ data: Week[] }>` |
| **排序** | `weekStart` 倒序 |

```js
const getTrainingWeekHistory = ({ openid, limit = 10, skip = 0 }) => {
  const db = wx.cloud.database()
  return db.collection('trainingWeeks')
    .where({ openid })
    .orderBy('weekStart', 'desc')
    .skip(skip)
    .limit(limit)
    .get()
}
```

#### getTrainingWeekDetail

| 项目 | 内容 |
|------|------|
| **函数名** | `getTrainingWeekDetail` |
| **输入** | `weekId: string` (文档 _id) |
| **返回** | `Promise<{ data: Week }>` |

```js
const getTrainingWeekDetail = (weekId) => {
  const db = wx.cloud.database()
  return db.collection('trainingWeeks').doc(weekId).get()
}
```

---

### 2.4 打卡 API

#### incrementExerciseSet

| 项目 | 内容 |
|------|------|
| **函数名** | `incrementExerciseSet` |
| **输入** | `{ weekDocId, dayIndex, exerciseIndex, weight, reps?, rpe?, note? }` |
| **返回** | `Promise<{ stats }>` |
| **原子更新** | `completedSets` 使用 `db.command.inc(1)` |
| **并发安全** | 是 |

```js
const incrementExerciseSet = ({ weekDocId, dayIndex, exerciseIndex, weight, reps, rpe, note }) => {
  const db = wx.cloud.database()
  const _ = db.command
  const now = new Date()
  
  const setDetail = { weight, completedAt: now }
  if (reps !== undefined) setDetail.reps = reps
  if (rpe !== undefined) setDetail.rpe = rpe
  if (note) setDetail.note = note
  
  return db.collection('trainingWeeks').doc(weekDocId).update({
    data: {
      [`days.${dayIndex}.exercises.${exerciseIndex}.completedSets`]: _.inc(1),
      [`days.${dayIndex}.exercises.${exerciseIndex}.setDetails`]: _.push(setDetail),
      updatedAt: now
    }
  })
}
```

#### updateSetDetail

| 项目 | 内容 |
|------|------|
| **函数名** | `updateSetDetail` |
| **输入** | `{ weekDocId, dayIndex, exerciseIndex, setIndex, weight?, rpe?, note? }` |
| **返回** | `Promise<{ stats }>` |
| **用途** | 修改已打卡的某组详情 |

```js
const updateSetDetail = ({ weekDocId, dayIndex, exerciseIndex, setIndex, weight, rpe, note }) => {
  const db = wx.cloud.database()
  const updates = { updatedAt: new Date() }
  
  const path = `days.${dayIndex}.exercises.${exerciseIndex}.setDetails.${setIndex}`
  if (weight !== undefined) updates[`${path}.weight`] = weight
  if (rpe !== undefined) updates[`${path}.rpe`] = rpe
  if (note !== undefined) updates[`${path}.note`] = note
  
  return db.collection('trainingWeeks').doc(weekDocId).update({ data: updates })
}
```

---

### 2.5 自定义动作 API

#### getCustomExercises

```js
const getCustomExercises = (openid) => {
  const db = wx.cloud.database()
  return db.collection('trainingExercises')
    .where({ openid, isDeleted: db.command.neq(true) })
    .orderBy('createdAt', 'desc')
    .get()
}
```

#### createCustomExercise

```js
const createCustomExercise = ({ openid, name, category, defaultSets, defaultReps, defaultWeight, videoLinks }) => {
  const db = wx.cloud.database()
  const now = new Date()
  return db.collection('trainingExercises').add({
    data: {
      openid, name, category,
      defaultSets: defaultSets || 3,
      defaultReps: defaultReps || 12,
      defaultWeight: defaultWeight || 0,
      videoLinks: videoLinks || [],
      isDeleted: false,
      createdAt: now,
      updatedAt: now
    }
  })
}
```

#### updateCustomExercise

```js
const updateCustomExercise = ({ exerciseId, name, category, defaultSets, defaultReps, defaultWeight, videoLinks }) => {
  const db = wx.cloud.database()
  return db.collection('trainingExercises').doc(exerciseId).update({
    data: { name, category, defaultSets, defaultReps, defaultWeight, videoLinks, updatedAt: new Date() }
  })
}
```

#### deleteCustomExercise

```js
const deleteCustomExercise = (exerciseId) => {
  const db = wx.cloud.database()
  return db.collection('trainingExercises').doc(exerciseId).update({
    data: { isDeleted: true, updatedAt: new Date() }
  })
}
```

---

### 2.6 教学视频 API

教学视频作为动作/模板的子字段，操作合并到上述 API 中：

| 操作 | 实现 |
|------|------|
| 添加视频到自定义动作 | `updateCustomExercise({ videoLinks: [...old, new] })` |
| 删除视频 | `updateCustomExercise({ videoLinks: filtered })` |
| 添加视频到模板项目 | `updateTrainingTemplate` 时修改 `days[n].exercises[m].videoLinks` |

---

### 2.7 工具函数

```js
// utils/training-time.js

/**
 * 获取 ISO 周标识
 */
function getWeekId(date = new Date()) {
  const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()))
  const dayNum = d.getUTCDay() || 7
  d.setUTCDate(d.getUTCDate() + 4 - dayNum)
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1))
  const weekNo = Math.ceil((((d - yearStart) / 86400000) + 1) / 7)
  return `${d.getUTCFullYear()}-W${String(weekNo).padStart(2, '0')}`
}

/**
 * 根据周标识获取周一到周日的日期数组
 */
function getWeekDates(weekId) {
  const [year, week] = weekId.split('-W').map(Number)
  const jan1 = new Date(Date.UTC(year, 0, 1))
  const days = (week - 1) * 7
  const dayOfWeek = jan1.getUTCDay() || 7
  const monday = new Date(jan1)
  monday.setUTCDate(jan1.getUTCDate() + days - dayOfWeek + 1)
  
  const dates = []
  for (let i = 0; i < 7; i++) {
    const d = new Date(monday)
    d.setUTCDate(monday.getUTCDate() + i)
    dates.push(d.toISOString().slice(0, 10))
  }
  return dates
}
```

---

## 3. 验收测试矩阵

| 编号 | 场景 | 预期结果 | 验证方法 |
|------|------|----------|----------|
| TC-01 | 用户无模板，打开训练页 | 显示空状态，引导创建模板 | 手动测试 |
| TC-02 | 首次创建模板 | 模板保存成功，当前周立即生成 | 检查 trainingTemplates + trainingWeeks |
| TC-03 | 同一日期重复生成周计划 | 不重复生成，返回已存在数据 | 调用 getOrCreateTrainingWeek 两次 |
| TC-04 | 模板修改后当前周不变化 | 当前周保持原数据，模板 version++ | 修改模板后检查周计划 |
| TC-05 | 下一周使用新模板 | 新周计划使用新模板内容 | 模拟跨周后生成新周 |
| TC-06 | 历史周保持快照 | 历史数据不受模板修改影响 | 查询历史周比对 |
| TC-07 | +1 正常增加 | completedSets + 1，setDetails 增加一条 | 点击后检查数据 |
| TC-08 | 完成数不能超过目标 | completedSets >= targetSets 时按钮禁用 | 前端 UI 测试 |
| TC-09 | 不同重量记录 | 每组 setDetail 记录独立重量 | 修改重量后检查 |
| TC-10 | RPE 和备注为空 | 字段可选，不传则不存 | 不填 RPE/备注打卡 |
| TC-11 | 第 4 条视频被拒绝 | 添加第 4 条时前端阻止 | 尝试添加 4 条 |
| TC-12 | 用户不能读写他人数据 | 查询/更新他人数据返回 0 | 用 openidB 查询 openidA 数据 |
| TC-13 | 网络失败 | 显示错误提示，不崩溃 | 断网测试 |
| TC-14 | 连续快速点击 +1 | 使用原子 inc，数据正确 | 快速点击 5 次检查 |
| TC-15 | 空动作日 | 显示"今天是休息日"提示 | 查看无动作的日期 |
| TC-16 | 自定义动作被引用后历史保留 | 周计划快照包含完整名称 | 删除自定义动作后检查历史周 |

---

## 4. 后续实施阶段

### 阶段 1：基础架构（可独立验收）

| 任务 | 文件 | 产出 |
|------|------|------|
| 修改 app.json 增加 training 页面和 tabBar | `app.json` | tabBar 3 项 |
| 创建空训练页 | `pages/training/*` | 空页面可显示 |
| 创建训练 API 文件 | `utils/training-api.js` | 空导出 |
| 创建固定动作库 | `utils/training-exercises.js` | 硬编码数据 |
| 创建 tabBar 图标 | `assets/icons/training*.png` | 两个图标 |

**验收点**：tabBar 可切换到训练页，显示空白页面。

---

### 阶段 2：模板功能

| 任务 | 文件 | 产出 |
|------|------|------|
| 实现 getTrainingTemplate | `utils/training-api.js` | API 函数 |
| 实现 createTrainingTemplate | `utils/training-api.js` | API 函数 |
| 实现 updateTrainingTemplate | `utils/training-api.js` | API 函数 |
| 创建模板编辑页 | `pages/training-template/*` | 完整页面 |
| 创建动作选择页 | `pages/training-exercise/*` | 完整页面 |
| 训练首页集成模板入口 | `pages/training/training.js` | 跳转逻辑 |

**验收点**：用户可创建、编辑、保存模板。

**回滚边界**：删除 training-template/、training-exercise/ 目录，恢复 training.js。

---

### 阶段 3：周计划与打卡

| 任务 | 文件 | 产出 |
|------|------|------|
| 实现 getOrCreateTrainingWeek | `utils/training-api.js` | API 函数 |
| 实现 incrementExerciseSet | `utils/training-api.js` | API 函数 |
| 创建 exercise-item 组件 | `components/exercise-item/*` | 打卡组件 |
| 训练首页展示周计划 | `pages/training/training.js` | 数据绑定 |
| 训练首页打卡交互 | `pages/training/training.js` | +1 逻辑 |
| 周切换（日期选择） | `pages/training/training.wxml` | UI 交互 |

**验收点**：用户可查看当前周计划并打卡。

**回滚边界**：删除 exercise-item/，恢复 training.js。

---

### 阶段 4：历史与详情

| 任务 | 文件 | 产出 |
|------|------|------|
| 实现 getTrainingWeekHistory | `utils/training-api.js` | API 函数 |
| 实现 getTrainingWeekDetail | `utils/training-api.js` | API 函数 |
| 实现 updateSetDetail | `utils/training-api.js` | API 函数 |
| 训练首页历史周入口 | `pages/training/training.wxml` | 周切换 UI |
| RPE/备注输入 | `components/exercise-item/*` | 可选输入 |

**验收点**：用户可查看历史周，修改打卡详情。

---

### 阶段 5：自定义动作与视频

| 任务 | 文件 | 产出 |
|------|------|------|
| 实现 getCustomExercises | `utils/training-api.js` | API 函数 |
| 实现 createCustomExercise | `utils/training-api.js` | API 函数 |
| 实现 updateCustomExercise | `utils/training-api.js` | API 函数 |
| 实现 deleteCustomExercise | `utils/training-api.js` | API 函数 |
| 动作选择页自定义入口 | `pages/training-exercise/*` | 创建动作 UI |
| 视频链接管理 | `pages/training-exercise/*` | 添加/删除/打开 |
| 视频外链降级 | `utils/training-api.js` | 复制到剪贴板 |

**验收点**：用户可创建自定义动作，管理视频链接。

---

### 阶段 6：打磨与优化

| 任务 | 文件 | 产出 |
|------|------|------|
| 空状态设计 | `pages/training/*` | 空状态 UI |
| 加载骨架屏 | `pages/training/*` | 加载状态 |
| 错误重试 | 所有页面 | 错误处理 |
| 性能优化 | `utils/training-api.js` | 减少云调用 |
| 样式对齐设计系统 | 所有页面 | 统一视觉 |

**验收点**：功能完整，体验流畅。

---

*本文档为数据模型与 API 合约，不修改任何运行代码。*
