// cloudfunctions/trainingService/lib/domain.js — 训练业务逻辑
// 本文件包含所有训练相关的数据库操作和业务规则

const time = require('./time')
const validation = require('./validation')
const logic = require('./domain-logic')

const { TRAINING_ERRORS } = validation

// ═══════════════════════════════════════════════════════════════
// 数据库集合名
// ═══════════════════════════════════════════════════════════════

const COLLECTIONS = {
  TEMPLATES: 'trainingTemplates',
  WEEKS: 'trainingWeeks',
  EXERCISES: 'trainingExercises'
}

// ═══════════════════════════════════════════════════════════════
// 错误响应工具
// ═══════════════════════════════════════════════════════════════

const success = (data = {}) => ({
  success: true,
  data
})

const fail = (error) => ({
  success: false,
  error: error || TRAINING_ERRORS.INTERNAL_ERROR
})

// ═══════════════════════════════════════════════════════════════
// 模板相关业务
// ═══════════════════════════════════════════════════════════════

/**
 * 获取用户活跃训练模板
 */
async function getTemplate(db, openid) {
  const result = await db.collection(COLLECTIONS.TEMPLATES)
    .where({ openid, status: 'active' })
    .limit(1)
    .get()
  
  if (result.data && result.data.length > 0) {
    return success({ template: result.data[0] })
  }
  
  return success({ template: null })
}

/**
 * 创建用户训练模板
 * 首次创建模板时，同时创建当前周的周计划
 * 返回值包含同步后的 week 对象
 */
async function createTemplate(db, openid, days) {
  // 校验模板数据
  const validationResult = validation.validateTemplateDays(days)
  if (!validationResult.valid) {
    return fail(validationResult.error)
  }

  // 检查是否已有活跃模板
  const existingResult = await db.collection(COLLECTIONS.TEMPLATES)
    .where({ openid, status: 'active' })
    .count()

  if (existingResult.total > 0) {
    return fail(TRAINING_ERRORS.TEMPLATE_EXISTS)
  }

  const now = new Date()
  // 使用纯函数创建标准化的模板对象
  const template = logic.createTemplateObject({ openid, days, now })

  const addResult = await db.collection(COLLECTIONS.TEMPLATES).add({ data: template })
  const templateId = addResult._id

  // 首次创建模板时，立即创建当前周的周计划
  const currentWeekId = time.getWeekId(now)

  // 构建周计划快照
  const templateWithId = { ...template, _id: templateId }
  const weekSnapshot = logic.buildWeekSnapshot({
    template: templateWithId,
    weekId: currentWeekId,
    now
  })

  // 调试日志
  const templateExerciseCount = template.days.reduce((sum, d) => sum + (d.exercises?.length || 0), 0)
  console.log('[createTemplate] 模板 version:', template.version, '动作总数:', templateExerciseCount)
  console.log('[createTemplate] weekId:', currentWeekId)

  let week = null
  try {
    const addWeekResult = await db.collection(COLLECTIONS.WEEKS).add({ data: weekSnapshot })
    // 获取刚创建的周计划
    const newWeekResult = await db.collection(COLLECTIONS.WEEKS).doc(addWeekResult._id).get()
    week = newWeekResult.data
  } catch (err) {
    if (!logic.isDuplicateKeyError(err)) {
      throw err
    }
    // 重复键错误：周计划已存在，执行同步
    console.log('[createTemplate] 周计划已存在，执行同步')
    const syncResult = await syncCurrentWeekInternal(db, openid, templateWithId, currentWeekId, now)
    if (!syncResult.success) {
      return syncResult
    }
    week = syncResult.data.week
  }

  // 验证同步结果
  const weekExerciseCount = (week?.days || []).reduce((sum, d) => sum + (d.exercises?.length || 0), 0)
  console.log('[createTemplate] 周动作总数:', weekExerciseCount)

  if (templateExerciseCount > 0 && weekExerciseCount === 0) {
    return fail({ code: 'SYNC_FAILED', message: '同步失败：模板有动作但周计划为空' })
  }

  return success({
    templateId,
    weekId: currentWeekId,
    version: 1,
    week
  })
}

/**
 * 更新用户训练模板并同步当前周
 * 返回值包含同步后的 week 对象
 */
async function updateTemplate(db, openid, days) {
  // 校验模板数据
  const validationResult = validation.validateTemplateDays(days)
  if (!validationResult.valid) {
    return fail(validationResult.error)
  }

  const now = new Date()
  const normalizedDays = logic.normalizeTemplateDays(days, now)

  // 使用事务原子更新 version
  const result = await db.collection(COLLECTIONS.TEMPLATES)
    .where({ openid, status: 'active' })
    .update({
      data: {
        days: normalizedDays,
        updatedAt: now,
        version: db.command.inc(1)
      }
    })

  if (result.stats.updated === 0) {
    return fail(TRAINING_ERRORS.TEMPLATE_NOT_FOUND)
  }

  // 获取更新后的完整模板
  const updatedTemplateResult = await db.collection(COLLECTIONS.TEMPLATES)
    .where({ openid, status: 'active' })
    .limit(1)
    .get()

  if (!updatedTemplateResult.data || updatedTemplateResult.data.length === 0) {
    return fail(TRAINING_ERRORS.TEMPLATE_NOT_FOUND)
  }

  const template = updatedTemplateResult.data[0]
  const currentWeekId = time.getWeekId(now)

  // 调试日志
  const templateExerciseCount = template.days.reduce((sum, d) => sum + (d.exercises?.length || 0), 0)
  console.log('[updateTemplate] 模板 version:', template.version, '动作总数:', templateExerciseCount)
  console.log('[updateTemplate] weekId:', currentWeekId)

  // 同步当前周计划
  const syncResult = await syncCurrentWeekInternal(db, openid, template, currentWeekId, now)
  if (!syncResult.success) {
    return syncResult
  }

  const week = syncResult.data.week
  const weekExerciseCount = (week?.days || []).reduce((sum, d) => sum + (d.exercises?.length || 0), 0)
  console.log('[updateTemplate] 同步后周动作总数:', weekExerciseCount)

  if (templateExerciseCount > 0 && weekExerciseCount === 0) {
    return fail({ code: 'SYNC_FAILED', message: '同步失败：模板有动作但周计划为空' })
  }

  return success({
    message: '模板已更新并同步到当前周',
    version: template.version,
    week
  })
}

// ═══════════════════════════════════════════════════════════════
// 周计划相关业务
// ═══════════════════════════════════════════════════════════════

/**
 * 获取或创建周计划
 * 实现幂等创建，只吞重复键错误
 */
async function getOrCreateWeek(db, openid, weekId) {
  // 默认当前周
  const targetWeekId = weekId || time.getWeekId(new Date())
  
  // 验证周标识格式和有效性
  if (!time.isValidWeekId(targetWeekId)) {
    return fail(TRAINING_ERRORS.WEEK_ID_INVALID)
  }
  
  // 1. 尝试获取已有的周计划
  const existingResult = await db.collection(COLLECTIONS.WEEKS)
    .where({ openid, weekId: targetWeekId })
    .limit(1)
    .get()
  
  if (existingResult.data && existingResult.data.length > 0) {
    return success({ week: existingResult.data[0] })
  }
  
  // 2. 没有周计划，需要从模板创建
  const templateResult = await db.collection(COLLECTIONS.TEMPLATES)
    .where({ openid, status: 'active' })
    .limit(1)
    .get()
  
  if (!templateResult.data || templateResult.data.length === 0) {
    return fail(TRAINING_ERRORS.TEMPLATE_NOT_FOUND)
  }
  
  const template = templateResult.data[0]
  const now = new Date()
  
  // 3. 使用纯函数构建周计划快照
  const weekSnapshot = logic.buildWeekSnapshot({
    template,
    weekId: targetWeekId,
    now
  })
  
  // 4. 尝试创建
  try {
    await db.collection(COLLECTIONS.WEEKS).add({ data: weekSnapshot })
  } catch (err) {
    // 5. 只处理重复键错误
    if (!logic.isDuplicateKeyError(err)) {
      throw err  // 其他错误继续抛出
    }
    // 重复键错误：重新查询并返回
  }
  
  // 6. 重新获取周计划
  const newResult = await db.collection(COLLECTIONS.WEEKS)
    .where({ openid, weekId: targetWeekId })
    .limit(1)
    .get()
  
  if (newResult.data && newResult.data.length > 0) {
    return success({ week: newResult.data[0] })
  }
  
  return fail(TRAINING_ERRORS.INTERNAL_ERROR)
}

/**
 * 获取周计划历史列表
 * 历史周定义：weekEnd（该周周日日期）早于今天本地日期
 */
async function getWeekHistory(db, openid, limit = 10, offset = 0) {
  const todayLocalDate = time.formatLocalDate(new Date())
  const currentWeekId = time.getWeekId(new Date())
  const _ = db.command

  const result = await db.collection(COLLECTIONS.WEEKS)
    .where({
      openid,
      weekEnd: _.lt(todayLocalDate)  // 只查询历史周：周结束日期早于今天
    })
    .orderBy('weekStart', 'desc')
    .skip(offset)
    .limit(limit)
    .get()

  console.log('[getWeekHistory]', {
    openid,
    todayLocalDate,
    currentWeekId,
    returned: (result.data || []).map(w => ({
      weekId: w.weekId,
      weekStart: w.weekStart,
      weekEnd: w.weekEnd
    }))
  })

  return success({
    weeks: result.data || [],
    total: result.data ? result.data.length : 0,
    currentWeekId,
    todayLocalDate
  })
}

// ═══════════════════════════════════════════════════════════════
// 打卡相关业务（事务实现）
// ═══════════════════════════════════════════════════════════════

/**
 * 打卡：增加一组（事务实现）
 * 使用 requestId 实现幂等性
 * 
 * @param {Object} db - 数据库实例
 * @param {string} openid - 用户标识
 * @param {string} weekDocId - 周计划文档 ID
 * @param {string} weekItemId - 项目标识
 * @param {Object} checkinData - 打卡数据
 */
async function incrementSet(db, openid, weekDocId, weekItemId, checkinData) {
  // 校验打卡输入
  const validationResult = validation.validateCheckinInput(checkinData)
  if (!validationResult.valid) {
    return fail(validationResult.error)
  }
  
  const { requestId, weight, reps, rpe, remark } = checkinData
  
  // 使用事务保证原子性
  const transaction = await db.startTransaction()
  
  try {
    // 1. 读取周计划
    const weekDoc = await transaction.collection(COLLECTIONS.WEEKS)
      .doc(weekDocId)
      .get()
    
    if (!weekDoc.data) {
      await transaction.rollback()
      return fail(TRAINING_ERRORS.WEEK_NOT_FOUND)
    }
    
    const week = weekDoc.data
    
    // 2. 验证所有权
    if (week.openid !== openid) {
      await transaction.rollback()
      return fail(TRAINING_ERRORS.UNAUTHORIZED)
    }
    
    // 3. 查找项目
    const itemLocation = logic.findWeekItem(week, weekItemId)
    if (!itemLocation) {
      await transaction.rollback()
      return fail(TRAINING_ERRORS.WEEK_ITEM_NOT_FOUND)
    }
    
    const { dayIndex, exerciseIndex, exercise } = itemLocation
    
    // 4. 验证打卡（幂等检查在目标上限检查之前）
    const validation = logic.validateIncrementSet(exercise, requestId)
    
    if (validation.duplicate) {
      await transaction.rollback()
      return success({
        duplicate: true,
        completedSets: exercise.completedSets,
        targetSets: exercise.targetSets,
        setDetail: validation.existingDetail
      })
    }
    
    if (validation.error) {
      await transaction.rollback()
      return fail(validation.error)
    }
    
    // 5. 创建新的组记录
    const now = new Date()
    const setDetail = logic.createSetDetail({
      requestId,
      setIndex: exercise.completedSets + 1,
      weight,
      reps,
      rpe,
      remark,
      targetReps: exercise.targetReps,
      now
    })
    
    // 6. 更新数据
    const updatePath = `days.${dayIndex}.exercises.${exerciseIndex}`
    
    await transaction.collection(COLLECTIONS.WEEKS)
      .doc(weekDocId)
      .update({
        data: {
          [`${updatePath}.setDetails`]: db.command.push(setDetail),
          [`${updatePath}.completedSets`]: exercise.completedSets + 1,
          updatedAt: now
        }
      })
    
    // 7. 提交事务
    await transaction.commit()
    
    return success({
      duplicate: false,
      completedSets: exercise.completedSets + 1,
      targetSets: exercise.targetSets,
      setDetail
    })
    
  } catch (err) {
    await transaction.rollback()
    throw err
  }
}

/**
 * 更新已完成组的详情
 * 通过 requestId 定位组记录
 */
async function updateSetDetail(db, openid, weekDocId, weekItemId, requestId, updateData) {
  // 校验更新数据
  if (updateData.weight !== undefined) {
    const weightResult = validation.validateNumber(updateData.weight, {
      min: 0, max: 1000,
      required: false,
      error: TRAINING_ERRORS.WEIGHT_INVALID
    })
    if (!weightResult.valid) {
      return fail(weightResult.error)
    }
  }
  
  if (updateData.reps !== undefined) {
    const repsResult = validation.validateInteger(updateData.reps, {
      min: 1, max: 999,
      error: TRAINING_ERRORS.REPS_INVALID
    })
    if (!repsResult.valid) {
      return fail(repsResult.error)
    }
  }
  
  if (updateData.rpe !== undefined && updateData.rpe !== null) {
    const rpeResult = validation.validateInteger(updateData.rpe, {
      min: 1, max: 10,
      required: false,
      error: TRAINING_ERRORS.RPE_INVALID
    })
    if (!rpeResult.valid) {
      return fail(rpeResult.error)
    }
  }
  
  // 获取周计划
  const weekDoc = await db.collection(COLLECTIONS.WEEKS)
    .doc(weekDocId)
    .get()
  
  if (!weekDoc.data) {
    return fail(TRAINING_ERRORS.WEEK_NOT_FOUND)
  }
  
  const week = weekDoc.data
  
  // 验证所有权
  if (week.openid !== openid) {
    return fail(TRAINING_ERRORS.UNAUTHORIZED)
  }
  
  // 查找项目
  const itemLocation = logic.findWeekItem(week, weekItemId)
  if (!itemLocation) {
    return fail(TRAINING_ERRORS.WEEK_ITEM_NOT_FOUND)
  }
  
  const { dayIndex, exerciseIndex, exercise } = itemLocation
  
  // 通过 requestId 查找组记录
  const setIdx = exercise.setDetails.findIndex(s => s.requestId === requestId)
  if (setIdx === -1) {
    return fail(TRAINING_ERRORS.WEEK_ITEM_NOT_FOUND)
  }
  
  // 构建更新对象（不允许修改 completedAt 和 setIndex）
  const now = new Date()
  const updateObj = { updatedAt: now }
  const basePath = `days.${dayIndex}.exercises.${exerciseIndex}.setDetails.${setIdx}`
  
  if (updateData.weight !== undefined) {
    updateObj[`${basePath}.weight`] = updateData.weight
  }
  if (updateData.reps !== undefined) {
    updateObj[`${basePath}.reps`] = updateData.reps
  }
  if (updateData.rpe !== undefined) {
    updateObj[`${basePath}.rpe`] = updateData.rpe
  }
  if (updateData.remark !== undefined) {
    updateObj[`${basePath}.remark`] = updateData.remark
  }
  
  await db.collection(COLLECTIONS.WEEKS)
    .doc(weekDocId)
    .update({ data: updateObj })
  
  return success({ message: '已更新' })
}

// ═══════════════════════════════════════════════════════════════
// 自定义动作相关业务（软删除）
// ═══════════════════════════════════════════════════════════════

/**
 * 获取用户自定义动作列表（排除已删除）
 */
async function getCustomExercises(db, openid) {
  const result = await db.collection(COLLECTIONS.EXERCISES)
    .where({
      openid,
      isDeleted: db.command.neq(true)
    })
    .orderBy('createdAt', 'desc')
    .get()
  
  return success({ exercises: result.data || [] })
}

/**
 * 创建自定义动作
 */
async function createCustomExercise(db, openid, exerciseData) {
  const validationResult = validation.validateCustomExerciseInput(exerciseData)
  if (!validationResult.valid) {
    return fail(validationResult.error)
  }
  
  const now = new Date()
  const exercise = logic.createCustomExerciseObject({ openid, exerciseData, now })
  
  const addResult = await db.collection(COLLECTIONS.EXERCISES).add({ data: exercise })
  
  return success({ exerciseId: addResult._id })
}

/**
 * 更新自定义动作
 */
async function updateCustomExercise(db, openid, exerciseId, exerciseData) {
  // 验证动作存在且属于当前用户且未删除
  const existing = await db.collection(COLLECTIONS.EXERCISES)
    .where({ _id: exerciseId, openid, isDeleted: db.command.neq(true) })
    .get()
  
  if (!existing.data || existing.data.length === 0) {
    return fail(TRAINING_ERRORS.CUSTOM_EXERCISE_NOT_FOUND)
  }
  
  const validationResult = validation.validateCustomExerciseInput(exerciseData)
  if (!validationResult.valid) {
    return fail(validationResult.error)
  }
  
  const now = new Date()
  const updateData = { updatedAt: now }
  
  if (exerciseData.name !== undefined) {
    updateData.name = String(exerciseData.name).trim()
  }
  if (exerciseData.englishName !== undefined) {
    updateData.englishName = String(exerciseData.englishName).trim()
  }
  if (exerciseData.category !== undefined) {
    updateData.category = String(exerciseData.category).trim()
  }
  if (exerciseData.itemType !== undefined) {
    updateData.itemType = exerciseData.itemType
  }
  if (exerciseData.defaultSets !== undefined) {
    updateData.defaultSets = exerciseData.defaultSets
  }
  if (exerciseData.defaultReps !== undefined) {
    updateData.defaultReps = exerciseData.defaultReps
  }
  if (exerciseData.defaultWeight !== undefined) {
    updateData.defaultWeight = exerciseData.defaultWeight
  }
  if (exerciseData.defaultDuration !== undefined) {
    updateData.defaultDuration = exerciseData.defaultDuration
  }
  if (exerciseData.videoLinks !== undefined) {
    updateData.videoLinks = logic.normalizeVideoLinks(exerciseData.videoLinks, now)
  }
  
  await db.collection(COLLECTIONS.EXERCISES)
    .doc(exerciseId)
    .update({ data: updateData })
  
  return success({ message: '已更新' })
}

/**
 * 删除自定义动作（软删除）
 */
async function deleteCustomExercise(db, openid, exerciseId) {
  const result = await db.collection(COLLECTIONS.EXERCISES)
    .where({ _id: exerciseId, openid, isDeleted: db.command.neq(true) })
    .update({
      data: {
        isDeleted: true,
        updatedAt: new Date()
      }
    })
  
  if (result.stats.updated === 0) {
    return fail(TRAINING_ERRORS.CUSTOM_EXERCISE_NOT_FOUND)
  }
  
  return success({ message: '已删除' })
}

// ═══════════════════════════════════════════════════════════════
// 视频相关业务（支持 scopeType）
// ═══════════════════════════════════════════════════════════════

/**
 * 添加视频
 * @param {Object} db - 数据库实例
 * @param {string} openid - 用户标识
 * @param {string} scopeType - "customExercise" | "templateItem"
 * @param {string} scopeId - 自定义动作 ID 或模板项目 itemId
 * @param {Object} videoData - { title, url }
 */
async function addVideo(db, openid, scopeType, scopeId, videoData) {
  const videoResult = validation.validateVideo(videoData)
  if (!videoResult.valid) {
    return fail(videoResult.error)
  }
  
  const now = new Date()
  const newVideo = logic.normalizeVideo({
    ...videoResult.value,
    videoId: logic.generateVideoId()
  }, now)
  
  if (scopeType === 'customExercise') {
    // 自定义动作
    const existing = await db.collection(COLLECTIONS.EXERCISES)
      .where({ _id: scopeId, openid, isDeleted: db.command.neq(true) })
      .get()
    
    if (!existing.data || existing.data.length === 0) {
      return fail(TRAINING_ERRORS.CUSTOM_EXERCISE_NOT_FOUND)
    }
    
    const exercise = existing.data[0]
    const currentVideos = exercise.videoLinks || []
    
    const validation = logic.validateAddVideo(currentVideos, newVideo.url)
    if (!validation.canAdd) {
      return fail(validation.error)
    }
    
    await db.collection(COLLECTIONS.EXERCISES)
      .doc(scopeId)
      .update({
        data: {
          videoLinks: db.command.push(newVideo),
          updatedAt: now
        }
      })
    
    return success({ videoId: newVideo.videoId })
    
  } else if (scopeType === 'templateItem') {
    // 模板项目
    const templateResult = await db.collection(COLLECTIONS.TEMPLATES)
      .where({ openid, status: 'active' })
      .get()
    
    if (!templateResult.data || templateResult.data.length === 0) {
      return fail(TRAINING_ERRORS.TEMPLATE_NOT_FOUND)
    }
    
    const template = templateResult.data[0]
    
    // 查找项目
    let dayIdx = -1
    let exIdx = -1
    for (let di = 0; di < template.days.length; di++) {
      const idx = template.days[di].exercises.findIndex(e => e.itemId === scopeId)
      if (idx !== -1) {
        dayIdx = di
        exIdx = idx
        break
      }
    }
    
    if (dayIdx === -1) {
      return fail(TRAINING_ERRORS.WEEK_ITEM_NOT_FOUND)
    }
    
    const exercise = template.days[dayIdx].exercises[exIdx]
    const currentVideos = exercise.videoLinks || []
    
    const validateResult = logic.validateAddVideo(currentVideos, newVideo.url)
    if (!validateResult.canAdd) {
      return fail(validateResult.error)
    }
    
    // 更新模板项目视频并增加版本号
    const videoPath = `days.${dayIdx}.exercises.${exIdx}.videoLinks`
    
    await db.collection(COLLECTIONS.TEMPLATES)
      .doc(template._id)
      .update({
        data: {
          [videoPath]: db.command.push(newVideo),
          updatedAt: now,
          version: db.command.inc(1)
        }
      })
    
    return success({ videoId: newVideo.videoId })
    
  } else {
    return fail(TRAINING_ERRORS.INVALID_INPUT)
  }
}

/**
 * 更新视频
 */
async function updateVideo(db, openid, scopeType, scopeId, videoId, videoData) {
  const videoResult = validation.validateVideo(videoData)
  if (!videoResult.valid) {
    return fail(videoResult.error)
  }
  
  const now = new Date()
  
  if (scopeType === 'customExercise') {
    const existing = await db.collection(COLLECTIONS.EXERCISES)
      .where({ _id: scopeId, openid, isDeleted: db.command.neq(true) })
      .get()
    
    if (!existing.data || existing.data.length === 0) {
      return fail(TRAINING_ERRORS.CUSTOM_EXERCISE_NOT_FOUND)
    }
    
    const exercise = existing.data[0]
    const videoInfo = logic.findVideoById(exercise.videoLinks, videoId)
    
    if (!videoInfo) {
      return fail(TRAINING_ERRORS.VIDEO_NOT_FOUND)
    }
    
    // 检查新 URL 是否与其他视频重复
    const otherUrls = exercise.videoLinks
      .filter((_, i) => i !== videoInfo.index)
      .map(v => v.url)
    
    if (otherUrls.includes(videoResult.value.url)) {
      return fail(TRAINING_ERRORS.VIDEO_DUPLICATE)
    }
    
    const updatedVideo = {
      ...videoInfo.video,
      title: videoResult.value.title,
      url: videoResult.value.url,
      updatedAt: now
    }
    
    const newVideoLinks = [...exercise.videoLinks]
    newVideoLinks[videoInfo.index] = updatedVideo
    
    await db.collection(COLLECTIONS.EXERCISES)
      .doc(scopeId)
      .update({
        data: {
          videoLinks: newVideoLinks,
          updatedAt: now
        }
      })
    
    return success({ message: '视频已更新' })
    
  } else if (scopeType === 'templateItem') {
    const templateResult = await db.collection(COLLECTIONS.TEMPLATES)
      .where({ openid, status: 'active' })
      .get()
    
    if (!templateResult.data || templateResult.data.length === 0) {
      return fail(TRAINING_ERRORS.TEMPLATE_NOT_FOUND)
    }
    
    const template = templateResult.data[0]
    
    // 查找项目
    let dayIdx = -1
    let exIdx = -1
    for (let di = 0; di < template.days.length; di++) {
      const idx = template.days[di].exercises.findIndex(e => e.itemId === scopeId)
      if (idx !== -1) {
        dayIdx = di
        exIdx = idx
        break
      }
    }
    
    if (dayIdx === -1) {
      return fail(TRAINING_ERRORS.WEEK_ITEM_NOT_FOUND)
    }
    
    const exercise = template.days[dayIdx].exercises[exIdx]
    const videoInfo = logic.findVideoById(exercise.videoLinks, videoId)
    
    if (!videoInfo) {
      return fail(TRAINING_ERRORS.VIDEO_NOT_FOUND)
    }
    
    const otherUrls = exercise.videoLinks
      .filter((_, i) => i !== videoInfo.index)
      .map(v => v.url)
    
    if (otherUrls.includes(videoResult.value.url)) {
      return fail(TRAINING_ERRORS.VIDEO_DUPLICATE)
    }
    
    const updatedVideo = {
      ...videoInfo.video,
      title: videoResult.value.title,
      url: videoResult.value.url,
      updatedAt: now
    }
    
    const newVideoLinks = [...exercise.videoLinks]
    newVideoLinks[videoInfo.index] = updatedVideo
    
    const videoPath = `days.${dayIdx}.exercises.${exIdx}.videoLinks`
    
    await db.collection(COLLECTIONS.TEMPLATES)
      .doc(template._id)
      .update({
        data: {
          [videoPath]: newVideoLinks,
          updatedAt: now,
          version: db.command.inc(1)
        }
      })
    
    return success({ message: '视频已更新' })
    
  } else {
    return fail(TRAINING_ERRORS.INVALID_INPUT)
  }
}

/**
 * 删除视频
 */
async function deleteVideo(db, openid, scopeType, scopeId, videoId) {
  const now = new Date()
  
  if (scopeType === 'customExercise') {
    const existing = await db.collection(COLLECTIONS.EXERCISES)
      .where({ _id: scopeId, openid, isDeleted: db.command.neq(true) })
      .get()
    
    if (!existing.data || existing.data.length === 0) {
      return fail(TRAINING_ERRORS.CUSTOM_EXERCISE_NOT_FOUND)
    }
    
    const exercise = existing.data[0]
    const videoInfo = logic.findVideoById(exercise.videoLinks, videoId)
    
    if (!videoInfo) {
      return fail(TRAINING_ERRORS.VIDEO_NOT_FOUND)
    }
    
    const newVideoLinks = exercise.videoLinks.filter((_, i) => i !== videoInfo.index)
    
    await db.collection(COLLECTIONS.EXERCISES)
      .doc(scopeId)
      .update({
        data: {
          videoLinks: newVideoLinks,
          updatedAt: now
        }
      })
    
    return success({ message: '视频已删除' })
    
  } else if (scopeType === 'templateItem') {
    const templateResult = await db.collection(COLLECTIONS.TEMPLATES)
      .where({ openid, status: 'active' })
      .get()
    
    if (!templateResult.data || templateResult.data.length === 0) {
      return fail(TRAINING_ERRORS.TEMPLATE_NOT_FOUND)
    }
    
    const template = templateResult.data[0]
    
    let dayIdx = -1
    let exIdx = -1
    for (let di = 0; di < template.days.length; di++) {
      const idx = template.days[di].exercises.findIndex(e => e.itemId === scopeId)
      if (idx !== -1) {
        dayIdx = di
        exIdx = idx
        break
      }
    }
    
    if (dayIdx === -1) {
      return fail(TRAINING_ERRORS.WEEK_ITEM_NOT_FOUND)
    }
    
    const exercise = template.days[dayIdx].exercises[exIdx]
    const videoInfo = logic.findVideoById(exercise.videoLinks, videoId)
    
    if (!videoInfo) {
      return fail(TRAINING_ERRORS.VIDEO_NOT_FOUND)
    }
    
    const newVideoLinks = exercise.videoLinks.filter((_, i) => i !== videoInfo.index)
    const videoPath = `days.${dayIdx}.exercises.${exIdx}.videoLinks`
    
    await db.collection(COLLECTIONS.TEMPLATES)
      .doc(template._id)
      .update({
        data: {
          [videoPath]: newVideoLinks,
          updatedAt: now,
          version: db.command.inc(1)
        }
      })
    
    return success({ message: '视频已删除' })

  } else {
    return fail(TRAINING_ERRORS.INVALID_INPUT)
  }
}

// ═══════════════════════════════════════════════════════════════
// 当前周同步（内部函数）
// ═══════════════════════════════════════════════════════════════

/**
 * 同步当前周计划（内部版本，供 createTemplate/updateTemplate 调用）
 * @param {Object} db - 数据库实例
 * @param {string} openid - 用户标识
 * @param {Object} template - 已更新的模板对象（含 _id）
 * @param {string} weekId - 周标识
 * @param {Date} now - 当前时间
 * @returns {Object} { success, data: { week } } 或 { success: false, error }
 */
async function syncCurrentWeekInternal(db, openid, template, weekId, now) {
  // 1. 获取当前周计划
  const weekResult = await db.collection(COLLECTIONS.WEEKS)
    .where({ openid, weekId })
    .limit(1)
    .get()

  if (!weekResult.data || weekResult.data.length === 0) {
    // 当前周不存在，直接创建
    const weekSnapshot = logic.buildWeekSnapshot({ template, weekId, now })

    try {
      const addResult = await db.collection(COLLECTIONS.WEEKS).add({ data: weekSnapshot })
      const newWeekResult = await db.collection(COLLECTIONS.WEEKS).doc(addResult._id).get()
      return success({ week: newWeekResult.data })
    } catch (err) {
      if (!logic.isDuplicateKeyError(err)) {
        throw err
      }
      // 重复键错误：重新查询
      const retryResult = await db.collection(COLLECTIONS.WEEKS)
        .where({ openid, weekId })
        .limit(1)
        .get()
      if (retryResult.data && retryResult.data.length > 0) {
        // 继续同步已有周计划
      } else {
        return fail(TRAINING_ERRORS.INTERNAL_ERROR)
      }
    }
  }

  // 2. 周计划已存在，执行同步
  const existingWeek = weekResult.data?.[0] || (await db.collection(COLLECTIONS.WEEKS).where({ openid, weekId }).limit(1).get()).data[0]

  const beforeExerciseCount = (existingWeek.days || []).reduce((sum, d) => sum + (d.exercises?.length || 0), 0)
  console.log('[syncCurrentWeekInternal] 同步前周动作数:', beforeExerciseCount)

  // 使用纯函数计算同步后的 days
  const syncedDays = logic.syncWeekWithTemplate({
    template,
    existingWeek,
    weekId,
    now
  })

  // 3. 更新周计划
  await db.collection(COLLECTIONS.WEEKS)
    .doc(existingWeek._id)
    .update({
      data: {
        days: syncedDays,
        templateVersion: template.version,
        updatedAt: now
      }
    })

  // 4. 返回更新后的周计划
  const updatedWeekResult = await db.collection(COLLECTIONS.WEEKS)
    .doc(existingWeek._id)
    .get()

  const afterExerciseCount = (updatedWeekResult.data?.days || []).reduce((sum, d) => sum + (d.exercises?.length || 0), 0)
  console.log('[syncCurrentWeekInternal] 同步后周动作数:', afterExerciseCount)

  return success({ week: updatedWeekResult.data })
}

// ═══════════════════════════════════════════════════════════════
// 当前周同步（公开接口）
// ═══════════════════════════════════════════════════════════════

/**
 * 同步当前周计划与模板
 * 模板保存后调用此接口，将模板变更应用到当前周
 */
async function syncCurrentWeek(db, openid) {
  const now = new Date()
  const currentWeekId = time.getWeekId(now)

  // 1. 获取最新模板
  const templateResult = await db.collection(COLLECTIONS.TEMPLATES)
    .where({ openid, status: 'active' })
    .limit(1)
    .get()

  if (!templateResult.data || templateResult.data.length === 0) {
    return fail(TRAINING_ERRORS.TEMPLATE_NOT_FOUND)
  }

  const template = templateResult.data[0]

  // 2. 获取当前周计划
  const weekResult = await db.collection(COLLECTIONS.WEEKS)
    .where({ openid, weekId: currentWeekId })
    .limit(1)
    .get()

  if (!weekResult.data || weekResult.data.length === 0) {
    // 当前周不存在，直接创建
    const weekSnapshot = logic.buildWeekSnapshot({
      template,
      weekId: currentWeekId,
      now
    })

    try {
      await db.collection(COLLECTIONS.WEEKS).add({ data: weekSnapshot })
    } catch (err) {
      if (!logic.isDuplicateKeyError(err)) {
        throw err
      }
    }

    // 重新获取
    const newWeekResult = await db.collection(COLLECTIONS.WEEKS)
      .where({ openid, weekId: currentWeekId })
      .limit(1)
      .get()

    return success({ week: newWeekResult.data[0], synced: true })
  }

  const existingWeek = weekResult.data[0]

  // 3. 使用纯函数计算同步后的 days
  const syncedDays = logic.syncWeekWithTemplate({
    template,
    existingWeek,
    weekId: currentWeekId,
    now
  })

  // 4. 更新周计划
  await db.collection(COLLECTIONS.WEEKS)
    .doc(existingWeek._id)
    .update({
      data: {
        days: syncedDays,
        templateVersion: template.version,
        updatedAt: now
      }
    })

  // 5. 返回更新后的周计划
  const updatedWeekResult = await db.collection(COLLECTIONS.WEEKS)
    .doc(existingWeek._id)
    .get()

  return success({ week: updatedWeekResult.data, synced: true })
}

// 导出模块
module.exports = {
  COLLECTIONS,
  success,
  fail,

  // 模板
  getTemplate,
  createTemplate,
  updateTemplate,

  // 周计划
  getOrCreateWeek,
  getWeekHistory,
  syncCurrentWeek,

  // 打卡
  incrementSet,
  updateSetDetail,

  // 自定义动作
  getCustomExercises,
  createCustomExercise,
  updateCustomExercise,
  deleteCustomExercise,

  // 视频
  addVideo,
  updateVideo,
  deleteVideo
}
