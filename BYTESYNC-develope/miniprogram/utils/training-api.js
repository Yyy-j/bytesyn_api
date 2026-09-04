// utils/training-api.js — 训练功能前端 API
// 封装所有训练相关的云函数调用

const { callCloudFunction } = require('./api')
const { getWeekId } = require('./training-time')

// 云函数名称
const CLOUD_FUNCTION = 'trainingService'

/**
 * 调用训练云函数
 * 统一错误处理：对 success: false 抛出带 code 的 Error
 * @param {string} action - 操作名称
 * @param {Object} payload - 请求数据
 * @returns {Promise<Object>} 返回 result.data
 */
const callTrainingService = async (action, payload = {}) => {
  // 获取 app 实例中的 openid（用于本地调试时传递）
  const app = getApp()
  const openid = app?.globalData?.openid

  const result = await callCloudFunction(CLOUD_FUNCTION, {
    action,
    payload,
    // 本地调试时云函数无法获取 OPENID，传递前端已获取的 openid
    _testOpenid: openid
  })
  
  if (!result || !result.success) {
    const error = new Error(
      result?.error?.message || '训练服务请求失败'
    )
    error.code = result?.error?.code || 'TRAINING_UNKNOWN_ERROR'
    throw error
  }
  
  return result.data
}

// ═══════════════════════════════════════════════════════════════
// 请求 ID 生成
// ═══════════════════════════════════════════════════════════════

/**
 * 生成唯一的请求 ID（用于幂等性）
 * @returns {string} 唯一标识符
 */
const createTrainingRequestId = () => {
  const timestamp = Date.now().toString(36)
  const random = Math.random().toString(36).substring(2, 10)
  return `tr_${timestamp}_${random}`
}

// ═══════════════════════════════════════════════════════════════
// 模板相关 API
// ═══════════════════════════════════════════════════════════════

/**
 * 获取用户训练模板
 * @returns {Promise<{ template: Object|null }>}
 */
const getTrainingTemplate = () => {
  return callTrainingService('getTemplate')
}

/**
 * 创建训练模板
 * @param {Array} days - 7天训练安排
 * @returns {Promise<{ templateId: string, weekId: string, version: number }>}
 */
const createTrainingTemplate = (days) => {
  return callTrainingService('createTemplate', { days })
}

/**
 * 更新训练模板
 * @param {Array} days - 新的7天训练安排
 * @returns {Promise<{ message: string, version: number }>}
 */
const updateTrainingTemplate = (days) => {
  return callTrainingService('updateTemplate', { days })
}

// ═══════════════════════════════════════════════════════════════
// 周计划相关 API
// ═══════════════════════════════════════════════════════════════

/**
 * 获取指定周的周计划
 * @param {string} [weekId] - 周标识，默认当前周
 * @returns {Promise<{ week: Object }>}
 */
const getTrainingWeek = (weekId) => {
  const targetWeekId = weekId || getWeekId(new Date())
  return callTrainingService('getOrCreateWeek', { weekId: targetWeekId })
}

/**
 * 获取或创建周计划
 * @param {string} [weekId] - 周标识，默认当前周
 * @returns {Promise<{ week: Object }>}
 */
const getOrCreateTrainingWeek = (weekId) => {
  return getTrainingWeek(weekId)
}

/**
 * 获取周计划历史列表
 * @param {Object} options - 分页选项
 * @param {number} [options.limit=10] - 每页数量
 * @param {number} [options.offset=0] - 偏移量
 * @returns {Promise<{ weeks: Array, total: number }>}
 */
const getTrainingWeekHistory = (options = {}) => {
  const { limit = 10, offset = 0 } = options
  return callTrainingService('getWeekHistory', { limit, offset })
}

/**
 * 同步当前周计划与模板
 * 模板保存后调用此接口，将模板变更应用到当前周
 * @returns {Promise<{ week: Object, synced: boolean }>}
 */
const syncCurrentTrainingWeek = () => {
  return callTrainingService('syncCurrentWeek')
}

// ═══════════════════════════════════════════════════════════════
// 打卡相关 API
// ═══════════════════════════════════════════════════════════════

/**
 * 打卡：完成一组
 * @param {Object} params - 打卡参数
 * @param {string} params.weekDocId - 周计划文档 ID
 * @param {string} params.weekItemId - 项目标识
 * @param {string} [params.requestId] - 请求ID（用于幂等，不传则自动生成）
 * @param {number} [params.weight] - 完成重量
 * @param {number} [params.reps] - 完成次数
 * @param {number} [params.rpe] - RPE (1-10)
 * @param {string} [params.remark] - 备注
 * @returns {Promise<{ duplicate: boolean, completedSets: number, targetSets: number, setDetail?: Object }>}
 */
const incrementExerciseSet = (params) => {
  const {
    weekDocId,
    weekItemId,
    requestId = createTrainingRequestId(),
    weight,
    reps,
    rpe,
    remark
  } = params
  
  return callTrainingService('incrementSet', {
    weekDocId,
    weekItemId,
    requestId,
    weight,
    reps,
    rpe,
    remark
  })
}

/**
 * 更新已完成组的详情
 * @param {Object} params - 更新参数
 * @param {string} params.weekDocId - 周计划文档 ID
 * @param {string} params.weekItemId - 项目标识
 * @param {string} params.requestId - 组记录的请求ID
 * @param {number} [params.weight] - 重量
 * @param {number} [params.reps] - 次数
 * @param {number} [params.rpe] - RPE
 * @param {string} [params.remark] - 备注
 * @returns {Promise<{ message: string }>}
 */
const updateExerciseSetDetail = (params) => {
  const { weekDocId, weekItemId, requestId, weight, reps, rpe, remark } = params
  
  return callTrainingService('updateSetDetail', {
    weekDocId,
    weekItemId,
    requestId,
    weight,
    reps,
    rpe,
    remark
  })
}

// ═══════════════════════════════════════════════════════════════
// 自定义动作相关 API
// ═══════════════════════════════════════════════════════════════

/**
 * 获取用户自定义动作列表
 * @returns {Promise<{ exercises: Array }>}
 */
const getCustomExercises = () => {
  return callTrainingService('getCustomExercises')
}

/**
 * 创建自定义动作
 * @param {Object} exerciseData - 动作数据
 * @param {string} exerciseData.name - 动作名称
 * @param {string} [exerciseData.englishName] - 英文名称
 * @param {string} [exerciseData.category='其他'] - 分类
 * @param {string} [exerciseData.itemType='strength'] - 项目类型
 * @param {number} [exerciseData.defaultSets] - 默认组数
 * @param {number} [exerciseData.defaultReps] - 默认次数
 * @param {number} [exerciseData.defaultWeight] - 默认重量
 * @param {number} [exerciseData.defaultDuration] - 默认时长（秒）
 * @param {Array} [exerciseData.videoLinks] - 视频链接
 * @returns {Promise<{ exerciseId: string }>}
 */
const createCustomExercise = (exerciseData) => {
  return callTrainingService('createCustomExercise', exerciseData)
}

/**
 * 更新自定义动作
 * @param {string} exerciseId - 动作ID
 * @param {Object} exerciseData - 要更新的数据
 * @returns {Promise<{ message: string }>}
 */
const updateCustomExercise = (exerciseId, exerciseData) => {
  return callTrainingService('updateCustomExercise', { exerciseId, ...exerciseData })
}

/**
 * 删除自定义动作（软删除）
 * @param {string} exerciseId - 动作ID
 * @returns {Promise<{ message: string }>}
 */
const deleteCustomExercise = (exerciseId) => {
  return callTrainingService('deleteCustomExercise', { exerciseId })
}

// ═══════════════════════════════════════════════════════════════
// 视频相关 API
// ═══════════════════════════════════════════════════════════════

/**
 * 添加视频
 * @param {Object} params - 参数
 * @param {string} params.scopeType - "customExercise" | "templateItem"
 * @param {string} params.scopeId - 自定义动作 ID 或模板项目 itemId
 * @param {string} params.title - 视频标题
 * @param {string} params.url - 视频URL (HTTPS)
 * @returns {Promise<{ videoId: string }>}
 */
const addTrainingVideo = (params) => {
  const { scopeType, scopeId, title, url } = params
  return callTrainingService('addVideo', { scopeType, scopeId, title, url })
}

/**
 * 更新视频
 * @param {Object} params - 参数
 * @param {string} params.scopeType - "customExercise" | "templateItem"
 * @param {string} params.scopeId - 自定义动作 ID 或模板项目 itemId
 * @param {string} params.videoId - 视频 ID
 * @param {string} params.title - 新标题
 * @param {string} params.url - 新URL
 * @returns {Promise<{ message: string }>}
 */
const updateTrainingVideo = (params) => {
  const { scopeType, scopeId, videoId, title, url } = params
  return callTrainingService('updateVideo', { scopeType, scopeId, videoId, title, url })
}

/**
 * 删除视频
 * @param {Object} params - 参数
 * @param {string} params.scopeType - "customExercise" | "templateItem"
 * @param {string} params.scopeId - 自定义动作 ID 或模板项目 itemId
 * @param {string} params.videoId - 视频 ID
 * @returns {Promise<{ message: string }>}
 */
const deleteTrainingVideo = (params) => {
  const { scopeType, scopeId, videoId } = params
  return callTrainingService('deleteVideo', { scopeType, scopeId, videoId })
}

// 导出模块
module.exports = {
  // 请求工具
  createTrainingRequestId,

  // 模板
  getTrainingTemplate,
  createTrainingTemplate,
  updateTrainingTemplate,

  // 周计划
  getTrainingWeek,
  getOrCreateTrainingWeek,
  getTrainingWeekHistory,
  syncCurrentTrainingWeek,

  // 打卡
  incrementExerciseSet,
  updateExerciseSetDetail,

  // 自定义动作
  getCustomExercises,
  createCustomExercise,
  updateCustomExercise,
  deleteCustomExercise,

  // 视频
  addTrainingVideo,
  updateTrainingVideo,
  deleteTrainingVideo
}
