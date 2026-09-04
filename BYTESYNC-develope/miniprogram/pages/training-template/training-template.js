// pages/training-template/training-template.js — 模板编辑页
// 编辑每周7天的训练安排

const {
  getTrainingTemplate,
  createTrainingTemplate,
  updateTrainingTemplate
} = require('../../utils/training-api')

const app = getApp()

// 星期名称
const DAY_NAMES = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

Page({
  data: {
    // 页面状态
    state: 'loading',  // loading | ready | saving | error
    errorMsg: '',
    
    // 是否已有模板
    hasTemplate: false,
    
    // 当前选中的天（0-6，对应周一到周日）
    currentDay: 0,
    dayNames: DAY_NAMES,
    
    // 7天模板数据
    days: [],
    
    // 当前天的动作列表（用于渲染）
    currentExercises: [],
    
    // 是否有未保存的修改
    isDirty: false,
    
    // 正在编辑的动作索引（-1 表示不在编辑）
    editingIndex: -1,
    
    // 编辑表单数据
    editForm: {
      targetSets: '',
      targetReps: '',
      targetWeight: '',
      targetDuration: ''
    },

    // 加载时已存在的 itemId 集合（用于判断是否已保存）
    savedItemIds: new Set()
  },

  onLoad(options) {
    // 从参数获取是否已有模板
    this.hasTemplate = options.hasTemplate === '1'
    this._loadTemplate()
  },

  onUnload() {
    // 页面卸载时不需要额外处理
  },

  /**
   * 页面返回前检查
   */
  onBackPress() {
    if (this.data.isDirty) {
      wx.showModal({
        title: '提示',
        content: '有未保存的修改，确定要离开吗？',
        success: (res) => {
          if (res.confirm) {
            wx.navigateBack()
          }
        }
      })
      return true
    }
    return false
  },

  /**
   * 加载模板数据
   */
  async _loadTemplate() {
    this.setData({ state: 'loading', errorMsg: '' })

    try {
      await app._initPromise

      if (this.hasTemplate) {
        // 加载已有模板
        const result = await getTrainingTemplate()
        if (result.template && result.template.days) {
          // 确保有7天数据
          const days = this._normalizeDays(result.template.days)
          // 记录已保存的 itemId
          const savedItemIds = new Set()
          days.forEach(day => {
            (day.exercises || []).forEach(ex => {
              if (ex.itemId) savedItemIds.add(ex.itemId)
            })
          })
          this.setData({
            hasTemplate: true,
            days,
            currentExercises: days[0].exercises || [],
            savedItemIds,
            state: 'ready'
          })
        } else {
          // 模板不存在，初始化空模板
          this._initEmptyTemplate()
        }
      } else {
        // 新用户，初始化空模板
        this._initEmptyTemplate()
      }
    } catch (err) {
      console.error('[training-template] 加载模板失败', err)
      this.setData({
        state: 'error',
        errorMsg: err.message || '加载失败'
      })
    }
  },

  /**
   * 初始化空的7天模板
   */
  _initEmptyTemplate() {
    const days = []
    for (let i = 0; i < 7; i++) {
      days.push({ dayIndex: i, exercises: [] })
    }
    this.setData({
      hasTemplate: false,
      days,
      currentExercises: [],
      savedItemIds: new Set(),
      state: 'ready'
    })
  },

  /**
   * 标准化天数据，确保有7天
   */
  _normalizeDays(inputDays) {
    const days = []
    for (let i = 0; i < 7; i++) {
      // 查找对应天的数据
      const existing = inputDays.find(d => d.dayIndex === i)
      if (existing) {
        days.push({
          dayIndex: i,
          exercises: existing.exercises || []
        })
      } else {
        days.push({ dayIndex: i, exercises: [] })
      }
    }
    return days
  },

  /**
   * 切换选中的天
   */
  onDayChange(e) {
    const dayIndex = e.currentTarget.dataset.day
    if (dayIndex === this.data.currentDay) return
    
    // 关闭编辑状态
    this.setData({
      currentDay: dayIndex,
      currentExercises: this.data.days[dayIndex].exercises || [],
      editingIndex: -1
    })
  },

  /**
   * 添加动作
   */
  onAddExercise() {
    const that = this
    wx.navigateTo({
      url: '/pages/training-exercise/training-exercise',
      events: {
        // 监听动作选择页返回的数据
        selectExercise(exercise) {
          that._addExerciseToDay(exercise)
        }
      }
    })
  },

  /**
   * 将动作添加到当前天
   */
  _addExerciseToDay(exercise) {
    const { currentDay, days } = this.data
    const currentDayData = days[currentDay]
    const exercises = currentDayData.exercises || []
    
    // 生成稳定唯一的 itemId
    const itemId = this._generateItemId()
    
    // 构建模板项目
    const item = {
      itemId,
      exerciseId: exercise.exerciseId,
      exerciseName: exercise.exerciseName,
      sourceType: exercise.sourceType,
      itemType: exercise.itemType,
      category: exercise.category || '',
      targetSets: Number(exercise.targetSets) || 4,
      targetReps: Number(exercise.targetReps) || 12,
      targetWeight: Number(exercise.targetWeight) || 0,
      targetDuration: Number(exercise.targetDuration) || 0,
      videoLinks: exercise.videoLinks || [],
      order: exercises.length
    }
    
    // 添加到列表
    exercises.push(item)
    
    // 更新数据
    const newDays = [...days]
    newDays[currentDay] = { ...currentDayData, exercises }
    
    this.setData({
      days: newDays,
      currentExercises: exercises,
      isDirty: true
    })
  },

  /**
   * 生成稳定唯一的 itemId
   */
  _generateItemId() {
    const timestamp = Date.now().toString(36)
    const random = Math.random().toString(36).substring(2, 8)
    return `item_${timestamp}_${random}`
  },

  /**
   * 删除动作
   */
  onDeleteExercise(e) {
    const index = e.currentTarget.dataset.index
    const { currentDay, days } = this.data
    const exercises = [...days[currentDay].exercises]
    
    wx.showModal({
      title: '确认删除',
      content: `确定要删除「${exercises[index].exerciseName}」吗？`,
      success: (res) => {
        if (res.confirm) {
          // 删除并更新 order
          exercises.splice(index, 1)
          exercises.forEach((ex, i) => { ex.order = i })
          
          const newDays = [...days]
          newDays[currentDay] = { ...newDays[currentDay], exercises }
          
          this.setData({
            days: newDays,
            currentExercises: exercises,
            isDirty: true,
            editingIndex: -1
          })
        }
      }
    })
  },

  /**
   * 上移动作
   */
  onMoveUp(e) {
    const index = e.currentTarget.dataset.index
    if (index <= 0) return
    
    this._swapExercises(index, index - 1)
  },

  /**
   * 下移动作
   */
  onMoveDown(e) {
    const index = e.currentTarget.dataset.index
    const { currentExercises } = this.data
    if (index >= currentExercises.length - 1) return
    
    this._swapExercises(index, index + 1)
  },

  /**
   * 交换两个动作的位置
   */
  _swapExercises(indexA, indexB) {
    const { currentDay, days } = this.data
    const exercises = [...days[currentDay].exercises]
    
    // 交换
    ;[exercises[indexA], exercises[indexB]] = [exercises[indexB], exercises[indexA]]
    
    // 更新 order
    exercises.forEach((ex, i) => { ex.order = i })
    
    const newDays = [...days]
    newDays[currentDay] = { ...newDays[currentDay], exercises }
    
    this.setData({
      days: newDays,
      currentExercises: exercises,
      isDirty: true
    })
  },

  /**
   * 开始编辑动作
   */
  onEditExercise(e) {
    const index = e.currentTarget.dataset.index
    const exercise = this.data.currentExercises[index]
    
    this.setData({
      editingIndex: index,
      editForm: {
        targetSets: String(exercise.targetSets || ''),
        targetReps: String(exercise.targetReps || ''),
        targetWeight: String(exercise.targetWeight || ''),
        targetDuration: String(exercise.targetDuration || '')
      }
    })
  },

  /**
   * 取消编辑
   */
  onCancelEdit() {
    this.setData({ editingIndex: -1 })
  },

  /**
   * 编辑表单输入
   */
  onEditFormInput(e) {
    const field = e.currentTarget.dataset.field
    this.setData({ [`editForm.${field}`]: e.detail.value })
  },

  /**
   * 保存编辑
   */
  onSaveEdit() {
    const { editingIndex, editForm, currentDay, days } = this.data
    if (editingIndex < 0) return
    
    const exercises = [...days[currentDay].exercises]
    const exercise = { ...exercises[editingIndex] }
    
    // 根据类型更新字段
    if (exercise.itemType === 'cardio') {
      // 有氧类型：使用时长
      const duration = Number(editForm.targetDuration)
      if (isNaN(duration) || duration < 1 || duration > 1440) {
        wx.showToast({ title: '时长需在 1-1440 秒之间', icon: 'none' })
        return
      }
      exercise.targetDuration = duration
    } else {
      // 力量类型：使用组数、次数、重量
      const sets = Number(editForm.targetSets)
      const reps = Number(editForm.targetReps)
      const weight = Number(editForm.targetWeight)
      
      if (isNaN(sets) || sets < 1 || sets > 50) {
        wx.showToast({ title: '组数需在 1-50 之间', icon: 'none' })
        return
      }
      if (isNaN(reps) || reps < 1 || reps > 999) {
        wx.showToast({ title: '次数需在 1-999 之间', icon: 'none' })
        return
      }
      if (isNaN(weight) || weight < 0 || weight > 1000) {
        wx.showToast({ title: '重量需在 0-1000 kg 之间', icon: 'none' })
        return
      }
      
      exercise.targetSets = sets
      exercise.targetReps = reps
      exercise.targetWeight = weight
    }
    
    exercises[editingIndex] = exercise
    
    const newDays = [...days]
    newDays[currentDay] = { ...newDays[currentDay], exercises }
    
    this.setData({
      days: newDays,
      currentExercises: exercises,
      editingIndex: -1,
      isDirty: true
    })
  },

  /**
   * 管理教学视频
   */
  onManageVideos(e) {
    const index = e.currentTarget.dataset.index
    const exercise = this.data.currentExercises[index]
    if (!exercise) return

    // 检查是否是已保存的动作
    if (!this.data.savedItemIds.has(exercise.itemId)) {
      wx.showToast({ title: '请先保存训练模板，再管理教学视频', icon: 'none', duration: 2500 })
      return
    }

    const that = this
    wx.navigateTo({
      url: `/pages/training-video/training-video?scopeType=templateItem&scopeId=${exercise.itemId}`,
      events: {
        // 接收视频链接变更
        videoLinksChanged(data) {
          that._updateExerciseVideoLinks(index, data.videoLinks || [])
        }
      },
      success(res) {
        // 发送当前视频链接
        res.eventChannel.emit('sendVideoLinks', {
          videoLinks: exercise.videoLinks || []
        })
      }
    })
  },

  /**
   * 更新动作的视频链接
   */
  _updateExerciseVideoLinks(index, videoLinks) {
    const { currentDay, days } = this.data
    const exercises = [...days[currentDay].exercises]

    if (!exercises[index]) return

    exercises[index] = { ...exercises[index], videoLinks }

    const newDays = [...days]
    newDays[currentDay] = { ...newDays[currentDay], exercises }

    this.setData({
      days: newDays,
      currentExercises: exercises,
      isDirty: true
    })
  },

  /**
   * 保存模板
   */
  async onSave() {
    if (this.data.state === 'saving') return

    this.setData({ state: 'saving' })

    try {
      const { days, hasTemplate } = this.data

      let result
      if (hasTemplate) {
        // 更新模板（后端自动同步当前周）
        result = await updateTrainingTemplate(days)
      } else {
        // 创建模板（后端自动同步当前周）
        result = await createTrainingTemplate(days)
      }

      // 验证返回的 week 包含动作
      const templateExerciseCount = days.reduce((sum, d) => sum + (d.exercises?.length || 0), 0)
      const weekExerciseCount = (result.week?.days || []).reduce((sum, d) => sum + (d.exercises?.length || 0), 0)

      console.log('[training-template] 模板动作数:', templateExerciseCount, '周动作数:', weekExerciseCount)

      if (templateExerciseCount > 0 && weekExerciseCount === 0) {
        throw new Error('同步失败：模板有动作但周计划为空，请重试')
      }

      wx.showToast({ title: '保存成功', icon: 'success' })

      // 清除修改标记
      this.setData({ isDirty: false })

      // 延迟返回
      setTimeout(() => {
        wx.navigateBack()
      }, 800)

    } catch (err) {
      console.error('[training-template] 保存失败', err)
      wx.showToast({ title: err.message || '保存失败', icon: 'none' })
      this.setData({ state: 'ready' })
    }
  },

  /**
   * 重试加载
   */
  onRetry() {
    this._loadTemplate()
  }
})
