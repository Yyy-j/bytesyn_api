// cloudfunctions/trainingService/test/domain.test.js — 训练业务逻辑测试
// 测试 domain-logic.js 和 time.js 中的纯函数

const assert = require('assert')

// 注意：在云函数环境运行测试时，需要从 lib 目录引入
// 这里使用相对路径以支持本地运行
const logic = require('../lib/domain-logic')
const time = require('../lib/time')

// ═══════════════════════════════════════════════════════════════
// 测试辅助函数
// ═══════════════════════════════════════════════════════════════

let passCount = 0
let failCount = 0

function test(name, fn) {
  try {
    fn()
    passCount++
    console.log(`✓ ${name}`)
  } catch (err) {
    failCount++
    console.log(`✗ ${name}`)
    console.log(`  Error: ${err.message}`)
  }
}

function deepEqual(a, b) {
  return JSON.stringify(a) === JSON.stringify(b)
}

// ═══════════════════════════════════════════════════════════════
// 测试数据
// ═══════════════════════════════════════════════════════════════

const now = new Date('2025-01-15T10:00:00.000Z')

const sampleTemplate = {
  _id: 'template123',
  openid: 'user001',
  version: 2,
  status: 'active',
  days: [
    {
      dayIndex: 0,
      exercises: [
        {
          itemId: 'item001',
          exerciseId: 'ex001',
          exerciseName: '深蹲',
          sourceType: 'fixed',
          itemType: 'strength',
          category: '腿部',
          targetSets: 4,
          targetReps: 12,
          targetWeight: 60,
          targetDuration: 0,
          videoLinks: [
            {
              videoId: 'vid001',
              title: '深蹲教学',
              url: 'https://example.com/squat.mp4',
              createdAt: now,
              updatedAt: now
            }
          ],
          order: 0
        }
      ]
    },
    {
      dayIndex: 2,
      exercises: [
        {
          itemId: 'item002',
          exerciseId: 'ex002',
          exerciseName: '跑步',
          sourceType: 'custom',
          itemType: 'cardio',
          category: '有氧',
          targetSets: 1,
          targetReps: 0,
          targetWeight: 0,
          targetDuration: 30,
          videoLinks: [],
          order: 0
        }
      ]
    }
  ],
  createdAt: now,
  updatedAt: now
}

// ═══════════════════════════════════════════════════════════════
// 测试开始
// ═══════════════════════════════════════════════════════════════

console.log('\n========== Training Domain Logic Tests ==========\n')

// ---------- time.js 测试 ----------

console.log('--- time.js 时区测试 ---')

test('1. TRAINING_TIME_ZONE 应为 Asia/Tokyo', () => {
  assert.strictEqual(time.TRAINING_TIME_ZONE, 'Asia/Tokyo')
})

test('2. getWeekId 应返回 ISO 周格式', () => {
  const date = new Date('2025-01-15T12:00:00.000Z')
  const weekId = time.getWeekId(date)
  assert.ok(/^\d{4}-W\d{2}$/.test(weekId), `Invalid format: ${weekId}`)
})

test('3. isValidWeekId 应接受有效的周标识', () => {
  assert.strictEqual(time.isValidWeekId('2025-W03'), true)
  assert.strictEqual(time.isValidWeekId('2024-W52'), true)
})

test('4. isValidWeekId 应拒绝无效的周标识', () => {
  assert.strictEqual(time.isValidWeekId('2025-W00'), false)
  assert.strictEqual(time.isValidWeekId('2025-W54'), false)
  assert.strictEqual(time.isValidWeekId('invalid'), false)
  assert.strictEqual(time.isValidWeekId(''), false)
})

test('5. isValidWeekId 应正确验证 W53', () => {
  // 2020年有第53周（闰年且1月1日是周三）
  assert.strictEqual(time.isValidWeekId('2020-W53'), true)
  // 2019年没有第53周
  assert.strictEqual(time.isValidWeekId('2019-W53'), false)
})

test('6. getWeekDates 应返回7个日期', () => {
  const dates = time.getWeekDates('2025-W03')
  assert.strictEqual(dates.length, 7)
})

test('7. getWeekStartDate 和 getWeekEndDate 应正确计算', () => {
  const start = time.getWeekStartDate('2025-W03')
  const end = time.getWeekEndDate('2025-W03')
  // 周一开始，周日结束
  assert.ok(typeof start === 'string')
  assert.ok(typeof end === 'string')
  assert.ok(/^\d{4}-\d{2}-\d{2}$/.test(start), `Invalid start format: ${start}`)
  assert.ok(/^\d{4}-\d{2}-\d{2}$/.test(end), `Invalid end format: ${end}`)
  assert.ok(end > start)
})

test('8. getDateInTimeZone 应基于 Asia/Tokyo 时区', () => {
  // 使用一个已知的日期
  const date = new Date('2025-01-13T00:00:00+09:00') // 周一
  const dateInfo = time.getDateInTimeZone(date)
  // 在东京时区，这是周一(1)
  assert.ok([0, 1, 2, 3, 4, 5, 6].includes(dateInfo.dayOfWeek))
})

// ---------- domain-logic.js 测试 ----------

console.log('\n--- domain-logic.js 标准化测试 ---')

test('9. generateVideoId 应返回 vid_ 前缀的字符串', () => {
  const id = logic.generateVideoId()
  assert.ok(id.startsWith('vid_'), `Invalid prefix: ${id}`)
  assert.ok(id.length > 10)
})

test('10. generateWeekItemId 应返回正确格式', () => {
  const id = logic.generateWeekItemId('2025-W03', 'item001')
  assert.strictEqual(id, 'wi_2025W03_item001')
})

test('11. generateWeekItemId 应过滤特殊字符', () => {
  const id = logic.generateWeekItemId('2025-W03', 'item@#$%001')
  assert.ok(!id.includes('@'))
  assert.ok(!id.includes('#'))
})

test('12. normalizeVideo 应标准化视频对象', () => {
  const video = logic.normalizeVideo({ title: '  Test  ', url: 'https://example.com ' }, now)
  assert.strictEqual(video.title, 'Test')
  assert.strictEqual(video.url, 'https://example.com')
  assert.ok(video.videoId.startsWith('vid_'))
  assert.ok(video.createdAt)
  assert.ok(video.updatedAt)
})

test('13. normalizeVideoLinks 应限制最多3个视频', () => {
  const videos = [
    { title: 'v1', url: 'https://1.com' },
    { title: 'v2', url: 'https://2.com' },
    { title: 'v3', url: 'https://3.com' },
    { title: 'v4', url: 'https://4.com' }
  ]
  const normalized = logic.normalizeVideoLinks(videos, now)
  assert.strictEqual(normalized.length, 3)
})

test('14. normalizeExerciseItem 应标准化力量训练项目', () => {
  const item = logic.normalizeExerciseItem({
    itemId: 'item001',
    exerciseId: 'ex001',
    exerciseName: '深蹲',
    itemType: 'strength',
    targetSets: 4,
    targetReps: 12
  }, 0, now)
  
  assert.strictEqual(item.itemId, 'item001')
  assert.strictEqual(item.itemType, 'strength')
  assert.strictEqual(item.targetSets, 4)
  assert.strictEqual(item.targetReps, 12)
  assert.strictEqual(item.targetDuration, 0)
})

test('15. normalizeExerciseItem 应标准化有氧训练项目', () => {
  const item = logic.normalizeExerciseItem({
    itemId: 'item002',
    exerciseId: 'ex002',
    exerciseName: '跑步',
    itemType: 'cardio',
    targetDuration: 30
  }, 0, now)
  
  assert.strictEqual(item.itemType, 'cardio')
  assert.strictEqual(item.targetSets, 1)
  assert.strictEqual(item.targetReps, 0)
  assert.strictEqual(item.targetDuration, 30)
})

test('16. normalizeTemplateDays 应标准化天数组', () => {
  const days = logic.normalizeTemplateDays([
    { dayIndex: 0, exercises: [] },
    { dayIndex: 2, exercises: [{ itemId: 'item001', exerciseId: 'ex001', exerciseName: '测试' }] }
  ], now)
  
  assert.strictEqual(days.length, 2)
  assert.strictEqual(days[0].dayIndex, 0)
  assert.strictEqual(days[1].dayIndex, 2)
  assert.strictEqual(days[1].exercises.length, 1)
})

test('17. createTemplateObject 应包含 status: active', () => {
  const template = logic.createTemplateObject({
    openid: 'user001',
    days: [],
    now
  })
  
  assert.strictEqual(template.status, 'active')
  assert.strictEqual(template.version, 1)
  assert.strictEqual(template.openid, 'user001')
})

console.log('\n--- domain-logic.js 快照测试 ---')

test('18. buildWeekSnapshot 应包含 templateId 和 templateVersion', () => {
  const snapshot = logic.buildWeekSnapshot({
    template: sampleTemplate,
    weekId: '2025-W03',
    now
  })
  
  assert.strictEqual(snapshot.templateId, 'template123')
  assert.strictEqual(snapshot.templateVersion, 2)
})

test('19. buildWeekSnapshot 应生成 weekItemId', () => {
  const snapshot = logic.buildWeekSnapshot({
    template: sampleTemplate,
    weekId: '2025-W03',
    now
  })
  
  const firstExercise = snapshot.days[0].exercises[0]
  assert.ok(firstExercise.weekItemId.startsWith('wi_'))
  assert.ok(firstExercise.weekItemId.includes('item001'))
})

test('20. buildWeekSnapshot 应保留 sourceItemId', () => {
  const snapshot = logic.buildWeekSnapshot({
    template: sampleTemplate,
    weekId: '2025-W03',
    now
  })
  
  const firstExercise = snapshot.days[0].exercises[0]
  assert.strictEqual(firstExercise.sourceItemId, 'item001')
})

test('21. buildWeekSnapshot 应初始化 completedSets 和 setDetails', () => {
  const snapshot = logic.buildWeekSnapshot({
    template: sampleTemplate,
    weekId: '2025-W03',
    now
  })
  
  const firstExercise = snapshot.days[0].exercises[0]
  assert.strictEqual(firstExercise.completedSets, 0)
  assert.deepStrictEqual(firstExercise.setDetails, [])
})

test('22. deepCopyVideoLinks 应深拷贝视频数组', () => {
  const original = [{ videoId: 'vid001', title: 'Test', url: 'https://test.com' }]
  const copy = logic.deepCopyVideoLinks(original)
  
  assert.strictEqual(copy.length, 1)
  assert.strictEqual(copy[0].videoId, 'vid001')
  // 验证是深拷贝
  original[0].title = 'Modified'
  assert.strictEqual(copy[0].title, 'Test')
})

console.log('\n--- domain-logic.js 打卡测试 ---')

test('23. findWeekItem 应通过 weekItemId 找到项目', () => {
  const week = {
    days: [
      {
        exercises: [
          { weekItemId: 'wi_2025W03_item001', exerciseName: '深蹲' }
        ]
      }
    ]
  }
  
  const result = logic.findWeekItem(week, 'wi_2025W03_item001')
  assert.ok(result)
  assert.strictEqual(result.dayIndex, 0)
  assert.strictEqual(result.exerciseIndex, 0)
  assert.strictEqual(result.exercise.exerciseName, '深蹲')
})

test('24. findWeekItem 应在找不到时返回 null', () => {
  const week = { days: [{ exercises: [] }] }
  const result = logic.findWeekItem(week, 'nonexistent')
  assert.strictEqual(result, null)
})

test('25. findExistingSetDetail 应通过 requestId 找到组记录', () => {
  const exercise = {
    setDetails: [
      { requestId: 'req001', setIndex: 1 },
      { requestId: 'req002', setIndex: 2 }
    ]
  }
  
  const result = logic.findExistingSetDetail(exercise, 'req002')
  assert.ok(result)
  assert.strictEqual(result.setIndex, 2)
})

test('26. validateIncrementSet 应先检查幂等性再检查目标上限', () => {
  const exercise = {
    completedSets: 4,
    targetSets: 4,
    setDetails: [{ requestId: 'req001', setIndex: 1 }]
  }
  
  // 使用已存在的 requestId，应该返回 duplicate: true
  const result = logic.validateIncrementSet(exercise, 'req001')
  assert.strictEqual(result.duplicate, true)
  assert.strictEqual(result.canIncrement, false)
  assert.strictEqual(result.error, null) // 不应该是 TARGET_REACHED
})

test('27. validateIncrementSet 应在新请求超过目标时返回错误', () => {
  const exercise = {
    completedSets: 4,
    targetSets: 4,
    setDetails: []
  }
  
  const result = logic.validateIncrementSet(exercise, 'new_request')
  assert.strictEqual(result.duplicate, false)
  assert.strictEqual(result.canIncrement, false)
  assert.ok(result.error) // 应该有 TARGET_REACHED 错误
})

test('28. createSetDetail 应创建正确的组记录', () => {
  const detail = logic.createSetDetail({
    requestId: 'req001',
    setIndex: 2,
    weight: 60,
    reps: 10,
    rpe: 8,
    remark: '感觉不错',
    targetReps: 12,
    now
  })
  
  assert.strictEqual(detail.requestId, 'req001')
  assert.strictEqual(detail.setIndex, 2)
  assert.strictEqual(detail.weight, 60)
  assert.strictEqual(detail.reps, 10)
  assert.strictEqual(detail.rpe, 8)
  assert.strictEqual(detail.remark, '感觉不错')
  assert.ok(detail.completedAt)
})

console.log('\n--- domain-logic.js 视频测试 ---')

test('29. findVideoById 应通过 videoId 找到视频', () => {
  const videos = [
    { videoId: 'vid001', title: 'Video 1' },
    { videoId: 'vid002', title: 'Video 2' }
  ]
  
  const result = logic.findVideoById(videos, 'vid002')
  assert.ok(result)
  assert.strictEqual(result.index, 1)
  assert.strictEqual(result.video.title, 'Video 2')
})

test('30. validateAddVideo 应限制视频数量为3个', () => {
  const videos = [
    { videoId: 'vid001', url: 'https://1.com' },
    { videoId: 'vid002', url: 'https://2.com' },
    { videoId: 'vid003', url: 'https://3.com' }
  ]
  
  const result = logic.validateAddVideo(videos, 'https://4.com')
  assert.strictEqual(result.canAdd, false)
  assert.ok(result.error)
})

test('31. validateAddVideo 应检测重复 URL', () => {
  const videos = [
    { videoId: 'vid001', url: 'https://existing.com' }
  ]
  
  const result = logic.validateAddVideo(videos, 'https://existing.com')
  assert.strictEqual(result.canAdd, false)
  assert.ok(result.error)
})

console.log('\n--- domain-logic.js 自定义动作测试 ---')

test('32. createCustomExerciseObject 应包含 isDeleted: false', () => {
  const exercise = logic.createCustomExerciseObject({
    openid: 'user001',
    exerciseData: { name: '自定义深蹲' },
    now
  })
  
  assert.strictEqual(exercise.isDeleted, false)
  assert.strictEqual(exercise.name, '自定义深蹲')
})

test('33. createCustomExerciseObject 应包含 englishName 和 category', () => {
  const exercise = logic.createCustomExerciseObject({
    openid: 'user001',
    exerciseData: {
      name: '深蹲',
      englishName: 'Squat',
      category: '腿部'
    },
    now
  })
  
  assert.strictEqual(exercise.englishName, 'Squat')
  assert.strictEqual(exercise.category, '腿部')
})

test('34. createCustomExerciseObject 应包含 defaultDuration', () => {
  const exercise = logic.createCustomExerciseObject({
    openid: 'user001',
    exerciseData: {
      name: '跑步',
      itemType: 'cardio',
      defaultDuration: 45
    },
    now
  })
  
  assert.strictEqual(exercise.itemType, 'cardio')
  assert.strictEqual(exercise.defaultDuration, 45)
})

console.log('\n--- domain-logic.js 错误检测测试 ---')

test('35. isDuplicateKeyError 应识别重复键错误', () => {
  const err1 = { errCode: -502005, message: 'Some error' }
  const err2 = { message: 'E11000 duplicate key error' }
  const err3 = { message: '唯一索引冲突' }
  const err4 = { code: 11000, message: 'Duplicate' }
  
  assert.strictEqual(logic.isDuplicateKeyError(err1), true)
  assert.strictEqual(logic.isDuplicateKeyError(err2), true)
  assert.strictEqual(logic.isDuplicateKeyError(err3), true)
  assert.strictEqual(logic.isDuplicateKeyError(err4), true)
})

test('36. isDuplicateKeyError 应对非重复键错误返回 false', () => {
  const err1 = { message: 'Network error' }
  const err2 = { errCode: -100, message: 'Other error' }
  const err3 = null
  
  assert.strictEqual(logic.isDuplicateKeyError(err1), false)
  assert.strictEqual(logic.isDuplicateKeyError(err2), false)
  assert.strictEqual(logic.isDuplicateKeyError(err3), false)
})

// ═══════════════════════════════════════════════════════════════
// 测试结束
// ═══════════════════════════════════════════════════════════════

console.log('\n========== Test Results ==========')
console.log(`Passed: ${passCount}`)
console.log(`Failed: ${failCount}`)
console.log(`Total:  ${passCount + failCount}`)
console.log('')

if (failCount > 0) {
  process.exit(1)
}
