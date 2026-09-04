// utils/training-validation.js — 训练数据校验工具
// 本文件提供训练功能所需的输入校验函数
// 所有校验返回 { valid: boolean, error?: { code, message } } 格式

// ═══════════════════════════════════════════════════════════════
// 错误码常量
// ═══════════════════════════════════════════════════════════════

const TRAINING_ERRORS = {
  // 通用错误
  INVALID_INPUT: { code: 'TRAINING_INVALID_INPUT', message: '输入参数无效' },
  UNAUTHORIZED: { code: 'TRAINING_UNAUTHORIZED', message: '无权访问此资源' },
  NOT_FOUND: { code: 'TRAINING_NOT_FOUND', message: '资源不存在' },
  
  // 模板错误
  TEMPLATE_DAYS_INVALID: { code: 'TRAINING_TEMPLATE_DAYS_INVALID', message: '模板必须包含完整的7天数据' },
  TEMPLATE_DAY_INDEX_INVALID: { code: 'TRAINING_TEMPLATE_DAY_INDEX_INVALID', message: '天索引必须为0-6的整数' },
  TEMPLATE_DAY_INDEX_DUPLICATE: { code: 'TRAINING_TEMPLATE_DAY_INDEX_DUPLICATE', message: '天索引不能重复' },
  TEMPLATE_EXERCISES_INVALID: { code: 'TRAINING_TEMPLATE_EXERCISES_INVALID', message: '每日训练项目必须是数组' },
  TEMPLATE_EXISTS: { code: 'TRAINING_TEMPLATE_EXISTS', message: '用户已有模板，请使用更新操作' },
  TEMPLATE_NOT_FOUND: { code: 'TRAINING_TEMPLATE_NOT_FOUND', message: '未找到训练模板' },
  
  // 项目错误
  ITEM_ID_REQUIRED: { code: 'TRAINING_ITEM_ID_REQUIRED', message: '项目ID必填' },
  EXERCISE_ID_REQUIRED: { code: 'TRAINING_EXERCISE_ID_REQUIRED', message: '动作ID必填' },
  EXERCISE_NAME_REQUIRED: { code: 'TRAINING_EXERCISE_NAME_REQUIRED', message: '动作名称必填' },
  EXERCISE_NAME_TOO_LONG: { code: 'TRAINING_EXERCISE_NAME_TOO_LONG', message: '动作名称不能超过40个字符' },
  SOURCE_TYPE_INVALID: { code: 'TRAINING_SOURCE_TYPE_INVALID', message: '来源类型只能是fixed或custom' },
  ITEM_TYPE_INVALID: { code: 'TRAINING_ITEM_TYPE_INVALID', message: '项目类型只能是strength或cardio' },
  TARGET_SETS_INVALID: { code: 'TRAINING_TARGET_SETS_INVALID', message: '目标组数必须是1-50的整数' },
  TARGET_REPS_INVALID: { code: 'TRAINING_TARGET_REPS_INVALID', message: '目标次数必须是1-999的整数' },
  TARGET_WEIGHT_INVALID: { code: 'TRAINING_TARGET_WEIGHT_INVALID', message: '目标重量必须是0-1000的数字' },
  TARGET_DURATION_INVALID: { code: 'TRAINING_TARGET_DURATION_INVALID', message: '目标时长必须是1-1440的整数（分钟）' },
  ORDER_INVALID: { code: 'TRAINING_ORDER_INVALID', message: '排序值不能为负数' },
  
  // 周计划错误
  WEEK_ID_INVALID: { code: 'TRAINING_WEEK_ID_INVALID', message: '周标识格式无效' },
  WEEK_NOT_FOUND: { code: 'TRAINING_WEEK_NOT_FOUND', message: '未找到周计划' },
  WEEK_ITEM_NOT_FOUND: { code: 'TRAINING_WEEK_ITEM_NOT_FOUND', message: '未找到周计划中的训练项目' },
  
  // 打卡错误
  REQUEST_ID_REQUIRED: { code: 'TRAINING_REQUEST_ID_REQUIRED', message: '请求ID必填' },
  TARGET_REACHED: { code: 'TRAINING_TARGET_REACHED', message: '已完成全部组数' },
  WEIGHT_INVALID: { code: 'TRAINING_WEIGHT_INVALID', message: '重量必须是0-1000的数字' },
  REPS_INVALID: { code: 'TRAINING_REPS_INVALID', message: '次数必须是1-999的整数' },
  RPE_INVALID: { code: 'TRAINING_RPE_INVALID', message: 'RPE必须是1-10的整数' },
  REMARK_TOO_LONG: { code: 'TRAINING_REMARK_TOO_LONG', message: '备注不能超过200个字符' },
  
  // 自定义动作错误
  CUSTOM_EXERCISE_NOT_FOUND: { code: 'TRAINING_CUSTOM_EXERCISE_NOT_FOUND', message: '未找到自定义动作' },
  
  // 视频错误
  VIDEO_LIMIT: { code: 'TRAINING_VIDEO_LIMIT', message: '每个项目最多添加3条视频' },
  VIDEO_TITLE_REQUIRED: { code: 'TRAINING_VIDEO_TITLE_REQUIRED', message: '视频标题必填' },
  VIDEO_TITLE_TOO_LONG: { code: 'TRAINING_VIDEO_TITLE_TOO_LONG', message: '视频标题不能超过60个字符' },
  VIDEO_URL_INVALID: { code: 'TRAINING_VIDEO_URL_INVALID', message: '视频链接必须是有效的HTTPS地址' },
  VIDEO_DUPLICATE: { code: 'TRAINING_VIDEO_DUPLICATE', message: '该视频链接已存在' },
  VIDEO_NOT_FOUND: { code: 'TRAINING_VIDEO_NOT_FOUND', message: '未找到该视频' }
}

// ═══════════════════════════════════════════════════════════════
// 基础校验工具
// ═══════════════════════════════════════════════════════════════

/**
 * 创建成功的校验结果
 */
const validResult = () => ({ valid: true })

/**
 * 创建失败的校验结果
 * @param {Object} error - 错误对象，包含 code 和 message
 */
const invalidResult = (error) => ({ valid: false, error })

/**
 * 校验字符串字段
 * @param {any} value - 待校验值
 * @param {Object} options - 配置项
 * @param {boolean} options.required - 是否必填
 * @param {number} options.maxLength - 最大长度
 * @param {Object} options.requiredError - 必填错误
 * @param {Object} options.lengthError - 长度错误
 */
const validateString = (value, options = {}) => {
  const { required = true, maxLength, requiredError, lengthError } = options
  
  // 检查类型
  if (value !== undefined && value !== null && typeof value !== 'string') {
    return invalidResult(requiredError || TRAINING_ERRORS.INVALID_INPUT)
  }
  
  // 去除首尾空格
  const trimmed = value ? String(value).trim() : ''
  
  // 检查必填
  if (required && !trimmed) {
    return invalidResult(requiredError || TRAINING_ERRORS.INVALID_INPUT)
  }
  
  // 检查长度
  if (maxLength && trimmed.length > maxLength) {
    return invalidResult(lengthError || TRAINING_ERRORS.INVALID_INPUT)
  }
  
  return { valid: true, value: trimmed }
}

/**
 * 校验整数字段
 * @param {any} value - 待校验值
 * @param {Object} options - 配置项
 * @param {number} options.min - 最小值
 * @param {number} options.max - 最大值
 * @param {boolean} options.required - 是否必填
 * @param {Object} options.error - 错误对象
 */
const validateInteger = (value, options = {}) => {
  const { min = 0, max = Number.MAX_SAFE_INTEGER, required = true, error } = options
  
  // 允许空值（非必填时）
  if (!required && (value === undefined || value === null || value === '')) {
    return { valid: true, value: null }
  }
  
  const num = Number(value)
  
  // 检查是否为有效整数
  if (!Number.isInteger(num) || num < min || num > max) {
    return invalidResult(error || TRAINING_ERRORS.INVALID_INPUT)
  }
  
  return { valid: true, value: num }
}

/**
 * 校验数字字段（可以是小数）
 * @param {any} value - 待校验值
 * @param {Object} options - 配置项
 */
const validateNumber = (value, options = {}) => {
  const { min = 0, max = Number.MAX_SAFE_INTEGER, required = true, error } = options
  
  // 允许空值（非必填时）
  if (!required && (value === undefined || value === null || value === '')) {
    return { valid: true, value: null }
  }
  
  const num = Number(value)
  
  // 检查是否为有效数字
  if (isNaN(num) || !isFinite(num) || num < min || num > max) {
    return invalidResult(error || TRAINING_ERRORS.INVALID_INPUT)
  }
  
  return { valid: true, value: num }
}

// ═══════════════════════════════════════════════════════════════
// 视频校验
// ═══════════════════════════════════════════════════════════════

/**
 * 校验 HTTPS URL 格式
 * @param {string} url - URL 字符串
 */
const isValidHttpsUrl = (url) => {
  if (!url || typeof url !== 'string') {
    return false
  }
  try {
    // 简单的 HTTPS URL 校验
    const pattern = /^https:\/\/[^\s/$.?#].[^\s]*$/i
    return pattern.test(url.trim())
  } catch {
    return false
  }
}

/**
 * 校验视频对象
 * @param {Object} video - 视频对象
 * @param {Array} existingUrls - 已存在的 URL 列表（用于检查重复）
 */
const validateVideo = (video, existingUrls = []) => {
  if (!video || typeof video !== 'object') {
    return invalidResult(TRAINING_ERRORS.INVALID_INPUT)
  }
  
  // 校验标题
  const titleResult = validateString(video.title, {
    required: true,
    maxLength: 60,
    requiredError: TRAINING_ERRORS.VIDEO_TITLE_REQUIRED,
    lengthError: TRAINING_ERRORS.VIDEO_TITLE_TOO_LONG
  })
  if (!titleResult.valid) {
    return titleResult
  }
  
  // 校验 URL
  const urlTrimmed = video.url ? String(video.url).trim() : ''
  if (!isValidHttpsUrl(urlTrimmed)) {
    return invalidResult(TRAINING_ERRORS.VIDEO_URL_INVALID)
  }
  
  // 检查重复
  if (existingUrls.includes(urlTrimmed)) {
    return invalidResult(TRAINING_ERRORS.VIDEO_DUPLICATE)
  }
  
  return {
    valid: true,
    value: {
      title: titleResult.value,
      url: urlTrimmed
    }
  }
}

/**
 * 校验视频链接数组
 * @param {Array} videoLinks - 视频链接数组
 */
const validateVideoLinks = (videoLinks) => {
  // 允许空数组
  if (!videoLinks) {
    return { valid: true, value: [] }
  }
  
  if (!Array.isArray(videoLinks)) {
    return invalidResult(TRAINING_ERRORS.INVALID_INPUT)
  }
  
  // 检查数量限制
  if (videoLinks.length > 3) {
    return invalidResult(TRAINING_ERRORS.VIDEO_LIMIT)
  }
  
  const validatedLinks = []
  const urls = []
  
  for (const video of videoLinks) {
    const result = validateVideo(video, urls)
    if (!result.valid) {
      return result
    }
    validatedLinks.push(result.value)
    urls.push(result.value.url)
  }
  
  return { valid: true, value: validatedLinks }
}

// ═══════════════════════════════════════════════════════════════
// 模板项目校验
// ═══════════════════════════════════════════════════════════════

/**
 * 校验单个训练项目
 * @param {Object} exercise - 训练项目对象
 */
const validateExerciseItem = (exercise) => {
  if (!exercise || typeof exercise !== 'object') {
    return invalidResult(TRAINING_ERRORS.INVALID_INPUT)
  }
  
  // 校验 itemId
  const itemIdResult = validateString(exercise.itemId, {
    required: true,
    maxLength: 100,
    requiredError: TRAINING_ERRORS.ITEM_ID_REQUIRED
  })
  if (!itemIdResult.valid) {
    return itemIdResult
  }
  
  // 校验 exerciseId
  const exerciseIdResult = validateString(exercise.exerciseId, {
    required: true,
    maxLength: 100,
    requiredError: TRAINING_ERRORS.EXERCISE_ID_REQUIRED
  })
  if (!exerciseIdResult.valid) {
    return exerciseIdResult
  }
  
  // 校验动作名称
  const nameResult = validateString(exercise.exerciseName, {
    required: true,
    maxLength: 40,
    requiredError: TRAINING_ERRORS.EXERCISE_NAME_REQUIRED,
    lengthError: TRAINING_ERRORS.EXERCISE_NAME_TOO_LONG
  })
  if (!nameResult.valid) {
    return nameResult
  }
  
  // 校验 sourceType
  const sourceType = exercise.sourceType
  if (sourceType !== 'fixed' && sourceType !== 'custom') {
    return invalidResult(TRAINING_ERRORS.SOURCE_TYPE_INVALID)
  }
  
  // 校验 itemType
  const itemType = exercise.itemType
  if (itemType !== 'strength' && itemType !== 'cardio') {
    return invalidResult(TRAINING_ERRORS.ITEM_TYPE_INVALID)
  }
  
  // 根据项目类型校验参数
  if (itemType === 'strength') {
    // 力量训练：校验组数和次数
    const setsResult = validateInteger(exercise.targetSets, {
      min: 1, max: 50,
      error: TRAINING_ERRORS.TARGET_SETS_INVALID
    })
    if (!setsResult.valid) {
      return setsResult
    }
    
    const repsResult = validateInteger(exercise.targetReps, {
      min: 1, max: 999,
      error: TRAINING_ERRORS.TARGET_REPS_INVALID
    })
    if (!repsResult.valid) {
      return repsResult
    }
  } else {
    // 有氧/时长类：校验时长
    const durationResult = validateInteger(exercise.targetDuration, {
      min: 1, max: 1440,
      error: TRAINING_ERRORS.TARGET_DURATION_INVALID
    })
    if (!durationResult.valid) {
      return durationResult
    }
  }
  
  // 校验重量（允许为0，自重动作）
  const weightResult = validateNumber(exercise.targetWeight, {
    min: 0, max: 1000,
    required: false,
    error: TRAINING_ERRORS.TARGET_WEIGHT_INVALID
  })
  if (!weightResult.valid) {
    return weightResult
  }
  
  // 校验排序值
  const orderResult = validateInteger(exercise.order, {
    min: 0, max: 9999,
    required: false,
    error: TRAINING_ERRORS.ORDER_INVALID
  })
  if (!orderResult.valid) {
    return orderResult
  }
  
  // 校验视频链接
  const videoResult = validateVideoLinks(exercise.videoLinks)
  if (!videoResult.valid) {
    return videoResult
  }
  
  return validResult()
}

// ═══════════════════════════════════════════════════════════════
// 模板校验
// ═══════════════════════════════════════════════════════════════

/**
 * 校验模板天数据
 * @param {Array} days - 天数据数组，应包含7天
 */
const validateTemplateDays = (days) => {
  // 检查是否为数组
  if (!Array.isArray(days)) {
    return invalidResult(TRAINING_ERRORS.TEMPLATE_DAYS_INVALID)
  }
  
  // 检查是否正好7天
  if (days.length !== 7) {
    return invalidResult(TRAINING_ERRORS.TEMPLATE_DAYS_INVALID)
  }
  
  // 收集所有 dayIndex 用于检查重复
  const dayIndexSet = new Set()
  
  for (const day of days) {
    if (!day || typeof day !== 'object') {
      return invalidResult(TRAINING_ERRORS.TEMPLATE_DAYS_INVALID)
    }
    
    // 校验 dayIndex
    const dayIndex = day.dayIndex
    if (!Number.isInteger(dayIndex) || dayIndex < 0 || dayIndex > 6) {
      return invalidResult(TRAINING_ERRORS.TEMPLATE_DAY_INDEX_INVALID)
    }
    
    // 检查重复
    if (dayIndexSet.has(dayIndex)) {
      return invalidResult(TRAINING_ERRORS.TEMPLATE_DAY_INDEX_DUPLICATE)
    }
    dayIndexSet.add(dayIndex)
    
    // 校验 exercises 数组
    if (!Array.isArray(day.exercises)) {
      return invalidResult(TRAINING_ERRORS.TEMPLATE_EXERCISES_INVALID)
    }
    
    // 校验每个训练项目
    for (const exercise of day.exercises) {
      const exerciseResult = validateExerciseItem(exercise)
      if (!exerciseResult.valid) {
        return exerciseResult
      }
    }
  }
  
  // 检查是否覆盖了所有7天（0-6）
  if (dayIndexSet.size !== 7) {
    return invalidResult(TRAINING_ERRORS.TEMPLATE_DAYS_INVALID)
  }
  
  return validResult()
}

// ═══════════════════════════════════════════════════════════════
// 打卡校验
// ═══════════════════════════════════════════════════════════════

/**
 * 校验打卡输入
 * @param {Object} checkinData - 打卡数据
 */
const validateCheckinInput = (checkinData) => {
  if (!checkinData || typeof checkinData !== 'object') {
    return invalidResult(TRAINING_ERRORS.INVALID_INPUT)
  }
  
  // 校验 requestId（必填，用于幂等）
  const requestIdResult = validateString(checkinData.requestId, {
    required: true,
    maxLength: 100,
    requiredError: TRAINING_ERRORS.REQUEST_ID_REQUIRED
  })
  if (!requestIdResult.valid) {
    return requestIdResult
  }
  
  // 校验重量（可以为0）
  const weightResult = validateNumber(checkinData.weight, {
    min: 0, max: 1000,
    required: false,
    error: TRAINING_ERRORS.WEIGHT_INVALID
  })
  if (!weightResult.valid) {
    return weightResult
  }
  
  // 校验次数（可选）
  if (checkinData.reps !== undefined && checkinData.reps !== null && checkinData.reps !== '') {
    const repsResult = validateInteger(checkinData.reps, {
      min: 1, max: 999,
      error: TRAINING_ERRORS.REPS_INVALID
    })
    if (!repsResult.valid) {
      return repsResult
    }
  }
  
  // 校验 RPE（可选，1-10）
  if (checkinData.rpe !== undefined && checkinData.rpe !== null && checkinData.rpe !== '') {
    const rpeResult = validateInteger(checkinData.rpe, {
      min: 1, max: 10,
      error: TRAINING_ERRORS.RPE_INVALID
    })
    if (!rpeResult.valid) {
      return rpeResult
    }
  }
  
  // 校验备注（可选）
  if (checkinData.remark !== undefined && checkinData.remark !== null) {
    const remarkResult = validateString(checkinData.remark, {
      required: false,
      maxLength: 200,
      lengthError: TRAINING_ERRORS.REMARK_TOO_LONG
    })
    if (!remarkResult.valid) {
      return remarkResult
    }
  }
  
  return validResult()
}

/**
 * 校验自定义动作输入
 * @param {Object} exerciseData - 动作数据
 */
const validateCustomExerciseInput = (exerciseData) => {
  if (!exerciseData || typeof exerciseData !== 'object') {
    return invalidResult(TRAINING_ERRORS.INVALID_INPUT)
  }
  
  // 校验名称
  const nameResult = validateString(exerciseData.name, {
    required: true,
    maxLength: 40,
    requiredError: TRAINING_ERRORS.EXERCISE_NAME_REQUIRED,
    lengthError: TRAINING_ERRORS.EXERCISE_NAME_TOO_LONG
  })
  if (!nameResult.valid) {
    return nameResult
  }
  
  // 校验 itemType（可选，默认 strength）
  const itemType = exerciseData.itemType || 'strength'
  if (itemType !== 'strength' && itemType !== 'cardio') {
    return invalidResult(TRAINING_ERRORS.ITEM_TYPE_INVALID)
  }
  
  // 校验默认组数（可选）
  if (exerciseData.defaultSets !== undefined) {
    const setsResult = validateInteger(exerciseData.defaultSets, {
      min: 1, max: 50,
      required: false,
      error: TRAINING_ERRORS.TARGET_SETS_INVALID
    })
    if (!setsResult.valid) {
      return setsResult
    }
  }
  
  // 校验默认次数（可选）
  if (exerciseData.defaultReps !== undefined) {
    const repsResult = validateInteger(exerciseData.defaultReps, {
      min: 1, max: 999,
      required: false,
      error: TRAINING_ERRORS.TARGET_REPS_INVALID
    })
    if (!repsResult.valid) {
      return repsResult
    }
  }
  
  // 校验默认重量（可选）
  if (exerciseData.defaultWeight !== undefined) {
    const weightResult = validateNumber(exerciseData.defaultWeight, {
      min: 0, max: 1000,
      required: false,
      error: TRAINING_ERRORS.TARGET_WEIGHT_INVALID
    })
    if (!weightResult.valid) {
      return weightResult
    }
  }
  
  // 校验视频链接
  if (exerciseData.videoLinks !== undefined) {
    const videoResult = validateVideoLinks(exerciseData.videoLinks)
    if (!videoResult.valid) {
      return videoResult
    }
  }
  
  return validResult()
}

// 导出模块
module.exports = {
  // 错误码
  TRAINING_ERRORS,
  
  // 基础校验
  validResult,
  invalidResult,
  validateString,
  validateInteger,
  validateNumber,
  
  // 视频校验
  isValidHttpsUrl,
  validateVideo,
  validateVideoLinks,
  
  // 项目和模板校验
  validateExerciseItem,
  validateTemplateDays,
  
  // 打卡校验
  validateCheckinInput,
  
  // 自定义动作校验
  validateCustomExerciseInput
}
