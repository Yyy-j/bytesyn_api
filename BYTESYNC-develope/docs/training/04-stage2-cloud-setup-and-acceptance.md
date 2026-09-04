# 阶段2：云端配置与验收指南

本文档说明训练功能云函数的部署配置步骤和验收测试方法。

## 1. 云函数部署

### 1.1 部署步骤

1. **打开微信开发者工具**
2. **上传云函数**
   - 右键点击 `cloudfunctions/trainingService` 文件夹
   - 选择「上传并部署：云端安装依赖」
   - 等待部署完成

3. **验证部署成功**
   - 打开云开发控制台
   - 进入「云函数」标签页
   - 确认 `trainingService` 出现在列表中

### 1.2 云函数配置

| 配置项 | 值 |
|--------|-----|
| 运行环境 | Node.js 16+ |
| 超时时间 | 20秒 |
| 内存 | 256MB |

## 2. 数据库集合配置

### 2.1 创建集合

在云开发控制台创建以下集合：

| 集合名 | 描述 |
|--------|------|
| `trainingTemplates` | 训练模板 |
| `trainingWeeks` | 周训练计划 |
| `trainingExercises` | 自定义动作 |

### 2.2 数据库索引

为提升查询性能，请创建以下索引：

#### trainingTemplates
```
字段: openid
类型: 普通索引
唯一: 是
```

#### trainingWeeks
```
字段: openid, weekId
类型: 组合索引
唯一: 是
```

```
字段: weekId
类型: 普通索引
唯一: 否
```

#### trainingExercises
```
字段: openid
类型: 普通索引
唯一: 否
```

### 2.3 数据库权限

所有集合设置为「仅创建者可读写」：

```json
{
  "read": "doc._openid == auth.openid",
  "write": "doc._openid == auth.openid"
}
```

> 注意：云函数使用管理员权限，不受此规则限制。

## 3. 本地测试

### 3.1 语法检查

```bash
cd /Users/zhengchengyin/Desktop/smallprogram/BYTESYNC

# 检查前端工具模块语法
node --check miniprogram/utils/training-exercises.js
node --check miniprogram/utils/training-time.js
node --check miniprogram/utils/training-validation.js
node --check miniprogram/utils/training-api.js

# 检查云函数语法
node --check cloudfunctions/trainingService/index.js
node --check cloudfunctions/trainingService/lib/time.js
node --check cloudfunctions/trainingService/lib/validation.js
node --check cloudfunctions/trainingService/lib/domain.js
```

### 3.2 运行单元测试

```bash
cd /Users/zhengchengyin/Desktop/smallprogram/BYTESYNC

# 运行纯逻辑测试
node cloudfunctions/trainingService/test/domain.test.js
```

期望输出：
```
--- 日期时间工具测试 ---
✓ formatLocalDate 返回 YYYY-MM-DD 格式
✓ parseLocalDate 正确解析日期字符串
...

--- 校验工具测试 ---
✓ validateString 必填字段校验
...

═══════════════════════════════════════════════
测试完成: 22 通过, 0 失败
═══════════════════════════════════════════════

所有测试通过! ✓
```

## 4. 验收测试清单

### 4.1 云函数 Actions 验收

| Action | 测试方法 | 预期结果 |
|--------|----------|----------|
| `getTemplate` | 新用户调用 | 返回 `{ success: true, template: null }` |
| `createTemplate` | 提交完整7天模板 | 返回 `{ success: true, templateId, weekId }` |
| `createTemplate` | 重复创建 | 返回 `TEMPLATE_EXISTS` 错误 |
| `updateTemplate` | 修改模板 | 返回成功，提示下周一生效 |
| `getOrCreateWeek` | 有模板时调用 | 返回当前周计划 |
| `getOrCreateWeek` | 无模板时调用 | 返回 `TEMPLATE_NOT_FOUND` |
| `incrementSet` | 完成一组 | `completedSets` 加 1 |
| `incrementSet` | 相同 requestId | 幂等返回，不重复计数 |
| `incrementSet` | 已达目标组数 | 返回 `TARGET_REACHED` |
| `addVideo` | 添加视频 | 成功添加 |
| `addVideo` | 第4条视频 | 返回 `VIDEO_LIMIT` |

### 4.2 数据安全验收

1. **OPENID 隔离测试**
   - 用户 A 创建模板
   - 用户 B 调用 getTemplate
   - 用户 B 应该看不到用户 A 的模板

2. **打卡幂等性测试**
   - 发送相同 requestId 两次
   - completedSets 只增加 1 次

### 4.3 边界条件验收

| 测试项 | 输入 | 预期 |
|--------|------|------|
| 动作名称 | 41字符 | 拒绝，返回 `EXERCISE_NAME_TOO_LONG` |
| 目标组数 | 0 | 拒绝，返回 `TARGET_SETS_INVALID` |
| 目标组数 | 51 | 拒绝，返回 `TARGET_SETS_INVALID` |
| RPE | 11 | 拒绝，返回 `RPE_INVALID` |
| 视频URL | http:// | 拒绝，返回 `VIDEO_URL_INVALID` |

## 5. 文件清单

### 5.1 前端模块

| 文件 | 说明 |
|------|------|
| `miniprogram/utils/training-exercises.js` | 27个固定动作库 |
| `miniprogram/utils/training-time.js` | ISO周日期工具 |
| `miniprogram/utils/training-validation.js` | 输入校验 |
| `miniprogram/utils/training-api.js` | 云函数调用封装 |

### 5.2 云函数

| 文件 | 说明 |
|------|------|
| `cloudfunctions/trainingService/index.js` | 主入口 |
| `cloudfunctions/trainingService/package.json` | 依赖配置 |
| `cloudfunctions/trainingService/lib/time.js` | 时间工具 |
| `cloudfunctions/trainingService/lib/validation.js` | 校验工具 |
| `cloudfunctions/trainingService/lib/domain.js` | 业务逻辑 |
| `cloudfunctions/trainingService/test/domain.test.js` | 单元测试 |

## 6. 下一步

阶段2完成后，可以开始阶段3的 UI 实现：

1. 模板编辑页面
2. 周计划展示页面
3. 打卡交互组件
4. 训练历史页面

---

*文档版本: 1.0*  
*最后更新: 2025-01*
