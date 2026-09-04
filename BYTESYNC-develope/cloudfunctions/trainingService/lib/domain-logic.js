// cloudfunctions/trainingService/lib/domain-logic.js — 纯业务逻辑
// 本文件只包含纯函数，不依赖数据库，便于单元测试

const time = require('./time')
const validation = require('./validation')

const { TRAINING_ERRORS } = validation

// ═══════════════════════════════════════════════════════════════
// 模板标准化
// ═══════════════════════════════════════════════════════════════

/**
 * 生成唯一的视频 ID
 * @returns {string}
 */
function generateVideoId() {
  const timestamp = Date.now().toString(36)
  const random = Math.random().toString(36).substring(2, 8)
  return `vid_${timestamp}_${random}`
}

/**
 * 标准化单个视频对象
 * @param {Object} video - 原始视频对象
 * @param {Date} now - 当前时间
 * @returns {Object} 标准化后的视频对象
 */
function normalizeVideo(video, now) {
  return {
    videoId: video.videoId || generateVideoId(),
    title: String(video.title || '').trim(),
    url: String(video.url || '').trim(),
    createdAt: video.createdAt || now,
    updatedAt: video.updatedAt || now
  }
}

/**
 * 标准化视频数组
 * @param {Array} videoLinks - 原始视频数组
 * @param {Date} now - 当前时间
 * @returns {Array} 标准化后的视频数组
 */
function normalizeVideoLinks(videoLinks, now) {
  if (!Array.isArray(videoLinks)) {
    return []
  }
  return videoLinks.slice(0, 3).map(v => normalizeVideo(v, now))
}

/**
 * 标准化单个训练项目（模板项目）
 * @param {Object} exercise - 原始项目对象
 * @param {number} order - 排序序号
 * @param {Date} now - 当前时间
 * @returns {Object} 标准化后的项目对象
 */
function normalizeExerciseItem(exercise, order, now) {
  const itemType = exercise.itemType || 'strength'
  
  const normalized = {
    itemId: String(exercise.itemId || '').trim(),
    exerciseId: String(exercise.exerciseId || '').trim(),
    exerciseName: String(exercise.exerciseName || '').trim(),
    sourceType: exercise.sourceType === 'custom' ? 'custom' : 'fixed',
    itemType: itemType,
    category: String(exercise.category || '').trim(),
    order: typeof order === 'number' ? order : 0,
    videoLinks: normalizeVideoLinks(exercise.videoLinks, now)
  }
  
  if (itemType === 'strength') {
    normalized.targetSets = Math.max(1, Math.min(50, parseInt(exercise.targetSets, 10) || 4))
    normalized.targetReps = Math.max(1, Math.min(999, parseInt(exercise.targetReps, 10) || 12))
    normalized.targetWeight = Math.max(0, Math.min(1000, parseFloat(exercise.targetWeight) || 0))
    normalized.targetDuration = 0
  } else {
    normalized.targetSets = 1
    normalized.targetReps = 0
    normalized.targetWeight = 0
    normalized.targetDuration = Math.max(1, Math.min(1440, parseInt(exercise.targetDuration, 10) || 30))
  }
  
  return normalized
}

/**
 * 标准化模板天数据
 * @param {Array} days - 原始天数据数组
 * @param {Date} now - 当前时间
 * @returns {Array} 标准化后的天数据数组
 */
function normalizeTemplateDays(days, now) {
  if (!Array.isArray(days)) {
    return []
  }
  
  return days.map(day => ({
    dayIndex: Math.max(0, Math.min(6, parseInt(day.dayIndex, 10) || 0)),
    exercises: Array.isArray(day.exercises)
      ? day.exercises.map((ex, idx) => normalizeExerciseItem(ex, idx, now))
      : []
  }))
}

/**
 * 创建完整的模板对象
 * @param {Object} params
 * @param {string} params.openid - 用户标识
 * @param {Array} params.days - 7天训练安排
 * @param {Date} params.now - 当前时间
 * @returns {Object} 完整的模板对象
 */
function createTemplateObject({ openid, days, now }) {
  return {
    openid,
    version: 1,
    status: 'active',
    days: normalizeTemplateDays(days, now),
    createdAt: now,
    updatedAt: now
  }
}

// ═══════════════════════════════════════════════════════════════
// 周计划快照
// ═══════════════════════════════════════════════════════════════

/**
 * 生成稳定的 weekItemId
 * 格式: wi_{weekId}_{sourceItemId}（字符标准化）
 * @param {string} weekId - 周标识
 * @param {string} sourceItemId - 模板项目 ID
 * @returns {string}
 */
function generateWeekItemId(weekId, sourceItemId) {
  // 移除特殊字符，只保留字母数字和下划线
  const safeWeekId = weekId.replace(/[^a-zA-Z0-9]/g, '')
  const safeItemId = String(sourceItemId).replace(/[^a-zA-Z0-9_]/g, '')
  return `wi_${safeWeekId}_${safeItemId}`
}

/**
 * 深拷贝视频数组（快照用）
 * @param {Array} videoLinks - 原始视频数组
 * @returns {Array} 深拷贝后的数组
 */
function deepCopyVideoLinks(videoLinks) {
  if (!Array.isArray(videoLinks)) {
    return []
  }
  return videoLinks.map(v => ({
    videoId: v.videoId,
    title: v.title,
    url: v.url,
    createdAt: v.createdAt,
    updatedAt: v.updatedAt
  }))
}

/**
 * 构建周计划快照（纯函数）
 * @param {Object} params
 * @param {Object} params.template - 模板对象
 * @param {string} params.weekId - 周标识
 * @param {Date} params.now - 当前时间
 * @returns {Object} 周计划快照对象
 */
function buildWeekSnapshot({ template, weekId, now }) {
  const weekDates = time.getWeekDates(weekId)
  
  const days = template.days.map(day => ({
    dayIndex: day.dayIndex,
    date: weekDates[day.dayIndex],
    exercises: day.exercises.map(exercise => ({
      weekItemId: generateWeekItemId(weekId, exercise.itemId),
      sourceItemId: exercise.itemId,
      exerciseId: exercise.exerciseId,
      exerciseName: exercise.exerciseName,
      sourceType: exercise.sourceType,
      itemType: exercise.itemType,
      category: exercise.category || '',
      targetSets: exercise.targetSets,
      targetReps: exercise.targetReps,
      targetWeight: exercise.targetWeight,
      targetDuration: exercise.targetDuration || 0,
      videoLinks: deepCopyVideoLinks(exercise.videoLinks),
      order: exercise.order,
      completedSets: 0,
      setDetails: []
    }))
  }))
  
  return {
    openid: template.openid,
    weekId,
    weekStart: time.getWeekStartDate(weekId),
    weekEnd: time.getWeekEndDate(weekId),
    templateId: template._id || null,
    templateVersion: template.version,
    snapshotAt: now,
    days,
    createdAt: now,
    updatedAt: now
  }
}

// ═══════════════════════════════════════════════════════════════
// 打卡逻辑（纯函数部分）
// ═══════════════════════════════════════════════════════════════

/**
 * 在周计划中查找项目
 * @param {Object} week - 周计划对象
 * @param {string} weekItemId - 项目标识
 * @returns {Object|null} { dayIndex, exerciseIndex, exercise } 或 null
 */
function findWeekItem(week, weekItemId) {
  for (let di = 0; di < week.days.length; di++) {
    const day = week.days[di]
    for (let ei = 0; ei < day.exercises.length; ei++) {
      const exercise = day.exercises[ei]
      if (exercise.weekItemId === weekItemId) {
        return {
          dayIndex: di,
          exerciseIndex: ei,
          exercise
        }
      }
    }
  }
  return null
}

/**
 * 检查打卡幂等性
 * @param {Object} exercise - 训练项目对象
 * @param {string} requestId - 请求 ID
 * @returns {Object|null} 已存在的组记录或 null
 */
function findExistingSetDetail(exercise, requestId) {
  if (!Array.isArray(exercise.setDetails)) {
    return null
  }
  return exercise.setDetails.find(d => d.requestId === requestId) || null
}

/**
 * 创建新的组记录
 * @param {Object} params
 * @param {string} params.requestId - 请求 ID
 * @param {number} params.setIndex - 组序号（从1开始）
 * @param {number} params.weight - 重量
 * @param {number} params.reps - 次数
 * @param {number} params.rpe - RPE
 * @param {string} params.remark - 备注
 * @param {number} params.targetReps - 目标次数（用于默认值）
 * @param {Date} params.now - 当前时间
 * @returns {Object} 组记录对象
 */
function createSetDetail({ requestId, setIndex, weight, reps, rpe, remark, targetReps, now }) {
  return {
    requestId,
    setIndex,
    weight: weight !== undefined && weight !== null ? Number(weight) : null,
    reps: reps !== undefined && reps !== null ? Number(reps) : targetReps,
    rpe: rpe !== undefined && rpe !== null ? Number(rpe) : null,
    remark: remark || null,
    completedAt: now
  }
}

/**
 * 验证打卡是否可执行
 * @param {Object} exercise - 训练项目对象
 * @param {string} requestId - 请求 ID
 * @returns {Object} { canIncrement, duplicate, existingDetail, error }
 */
function validateIncrementSet(exercise, requestId) {
  // 先检查幂等性
  const existingDetail = findExistingSetDetail(exercise, requestId)
  if (existingDetail) {
    return {
      canIncrement: false,
      duplicate: true,
      existingDetail,
      error: null
    }
  }
  
  // 再检查目标上限
  if (exercise.completedSets >= exercise.targetSets) {
    return {
      canIncrement: false,
      duplicate: false,
      existingDetail: null,
      error: TRAINING_ERRORS.TARGET_REACHED
    }
  }
  
  return {
    canIncrement: true,
    duplicate: false,
    existingDetail: null,
    error: null
  }
}

// ═══════════════════════════════════════════════════════════════
// 视频逻辑
// ═══════════════════════════════════════════════════════════════

/**
 * 在数组中通过 videoId 查找视频
 * @param {Array} videoLinks - 视频数组
 * @param {string} videoId - 视频 ID
 * @returns {Object|null} { index, video } 或 null
 */
function findVideoById(videoLinks, videoId) {
  if (!Array.isArray(videoLinks)) {
    return null
  }
  const index = videoLinks.findIndex(v => v.videoId === videoId)
  if (index === -1) {
    return null
  }
  return { index, video: videoLinks[index] }
}

/**
 * 验证视频添加
 * @param {Array} currentVideos - 当前视频数组
 * @param {string} newUrl - 新视频 URL
 * @returns {Object} { canAdd, error }
 */
function validateAddVideo(currentVideos, newUrl) {
  const videos = currentVideos || []
  
  if (videos.length >= 3) {
    return { canAdd: false, error: TRAINING_ERRORS.VIDEO_LIMIT }
  }
  
  if (videos.some(v => v.url === newUrl)) {
    return { canAdd: false, error: TRAINING_ERRORS.VIDEO_DUPLICATE }
  }
  
  return { canAdd: true, error: null }
}

// ═══════════════════════════════════════════════════════════════
// 自定义动作
// ═══════════════════════════════════════════════════════════════

/**
 * 创建自定义动作对象
 * @param {Object} params
 * @param {string} params.openid - 用户标识
 * @param {Object} params.exerciseData - 动作数据
 * @param {Date} params.now - 当前时间
 * @returns {Object} 自定义动作对象
 */
function createCustomExerciseObject({ openid, exerciseData, now }) {
  const itemType = exerciseData.itemType || 'strength'
  
  const exercise = {
    openid,
    name: String(exerciseData.name || '').trim(),
    englishName: String(exerciseData.englishName || '').trim(),
    category: String(exerciseData.category || '其他').trim(),
    itemType,
    sourceType: 'custom',  // 标记为自定义动作
    isDeleted: false,
    createdAt: now,
    updatedAt: now
  }
  
  if (itemType === 'strength') {
    exercise.defaultSets = Math.max(1, Math.min(50, parseInt(exerciseData.defaultSets, 10) || 4))
    exercise.defaultReps = Math.max(1, Math.min(999, parseInt(exerciseData.defaultReps, 10) || 12))
    exercise.defaultWeight = Math.max(0, Math.min(1000, parseFloat(exerciseData.defaultWeight) || 0))
    exercise.defaultDuration = 0
  } else {
    exercise.defaultSets = 1
    exercise.defaultReps = 0
    exercise.defaultWeight = 0
    exercise.defaultDuration = Math.max(1, Math.min(1440, parseInt(exerciseData.defaultDuration, 10) || 30))
  }
  
  exercise.videoLinks = normalizeVideoLinks(exerciseData.videoLinks, now)
  
  return exercise
}

// ═══════════════════════════════════════════════════════════════
// 数据库错误检测
// ═══════════════════════════════════════════════════════════════

/**
 * 判断是否为重复键错误
 * @param {Error} err - 错误对象
 * @returns {boolean}
 */
function isDuplicateKeyError(err) {
  if (!err) return false

  const message = err.message || ''
  const errCode = err.errCode || err.code

  // 微信云数据库重复键错误
  if (errCode === -502005) return true
  if (errCode === 11000) return true

  // MongoDB 重复键错误模式
  if (message.includes('duplicate key')) return true
  if (message.includes('E11000')) return true
  if (message.includes('唯一索引冲突')) return true

  return false
}

// ═══════════════════════════════════════════════════════════════
// 当前周同步逻辑
// ═══════════════════════════════════════════════════════════════

/**
 * 同步当前周计划与模板
 * 按 itemId 匹配，保留打卡记录
 *
 * @param {Object} params
 * @param {Object} params.template - 最新模板
 * @param {Object} params.existingWeek - 当前周计划
 * @param {string} params.weekId - 周标识
 * @param {Date} params.now - 当前时间
 * @returns {Object} 同步后的周计划 days 数组
 */
function syncWeekWithTemplate({ template, existingWeek, weekId, now }) {
  const weekDates = time.getWeekDates(weekId)

  // 建立现有周计划的 sourceItemId -> exercise 映射（所有天）
  const existingMap = new Map()
  for (const day of existingWeek.days || []) {
    for (const ex of day.exercises || []) {
      if (ex.sourceItemId) {
        existingMap.set(ex.sourceItemId, ex)
      }
    }
  }

  // 按模板重建每天的动作列表
  const syncedDays = template.days.map(templateDay => {
    const dayIndex = templateDay.dayIndex
    const exercises = (templateDay.exercises || []).map(templateEx => {
      const existing = existingMap.get(templateEx.itemId)

      if (existing) {
        // 已存在：保留 weekItemId、completedSets、setDetails，同步其他字段
        // targetSets 不得小于 completedSets
        const newTargetSets = Math.max(templateEx.targetSets, existing.completedSets || 0)

        return {
          weekItemId: existing.weekItemId,
          sourceItemId: templateEx.itemId,
          exerciseId: templateEx.exerciseId,
          exerciseName: templateEx.exerciseName,
          sourceType: templateEx.sourceType,
          itemType: templateEx.itemType,
          category: templateEx.category || '',
          targetSets: newTargetSets,
          targetReps: templateEx.targetReps,
          targetWeight: templateEx.targetWeight,
          targetDuration: templateEx.targetDuration || 0,
          videoLinks: deepCopyVideoLinks(templateEx.videoLinks),
          order: templateEx.order,
          completedSets: existing.completedSets || 0,
          setDetails: existing.setDetails || []
        }
      } else {
        // 新增：创建新的周计划项目
        return {
          weekItemId: generateWeekItemId(weekId, templateEx.itemId),
          sourceItemId: templateEx.itemId,
          exerciseId: templateEx.exerciseId,
          exerciseName: templateEx.exerciseName,
          sourceType: templateEx.sourceType,
          itemType: templateEx.itemType,
          category: templateEx.category || '',
          targetSets: templateEx.targetSets,
          targetReps: templateEx.targetReps,
          targetWeight: templateEx.targetWeight,
          targetDuration: templateEx.targetDuration || 0,
          videoLinks: deepCopyVideoLinks(templateEx.videoLinks),
          order: templateEx.order,
          completedSets: 0,
          setDetails: []
        }
      }
    })

    // 查找模板中已删除但有打卡记录的动作，需要保留
    const templateItemIds = new Set((templateDay.exercises || []).map(e => e.itemId))
    const existingDay = (existingWeek.days || []).find(d => d.dayIndex === dayIndex)

    if (existingDay) {
      for (const oldEx of existingDay.exercises || []) {
        if (oldEx.sourceItemId && !templateItemIds.has(oldEx.sourceItemId)) {
          // 模板中已删除
          if (oldEx.completedSets > 0 || (oldEx.setDetails && oldEx.setDetails.length > 0)) {
            // 有打卡记录，保留
            exercises.push({
              ...oldEx,
              order: exercises.length  // 放到最后
            })
          }
          // 无打卡记录，不保留（自动删除）
        }
      }
    }

    return {
      dayIndex,
      date: weekDates[dayIndex],
      exercises
    }
  })

  return syncedDays
}

// 导出所有纯函数
module.exports = {
  // 工具函数
  generateVideoId,
  generateWeekItemId,
  isDuplicateKeyError,
  
  // 标准化
  normalizeVideo,
  normalizeVideoLinks,
  normalizeExerciseItem,
  normalizeTemplateDays,
  createTemplateObject,
  
  // 快照
  deepCopyVideoLinks,
  buildWeekSnapshot,
  
  // 打卡
  findWeekItem,
  findExistingSetDetail,
  createSetDetail,
  validateIncrementSet,
  
  // 视频
  findVideoById,
  validateAddVideo,

  // 自定义动作
  createCustomExerciseObject,

  // 当前周同步
  syncWeekWithTemplate,

  // 重新导出错误常量
  TRAINING_ERRORS
}
