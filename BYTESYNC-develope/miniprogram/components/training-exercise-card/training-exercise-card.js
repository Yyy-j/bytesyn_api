// components/training-exercise-card/training-exercise-card.js — 训练打卡组件
// 显示单个动作的打卡进度和已完成组详情，支持编辑

const { incrementExerciseSet, updateExerciseSetDetail, createTrainingRequestId } = require('../../utils/training-api')

Component({
  properties: {
    // 训练项目数据
    exercise: {
      type: Object,
      value: {}
    },
    // 周计划文档 ID
    weekDocId: {
      type: String,
      value: ''
    },
    // 只读模式（历史页面使用）
    readonly: {
      type: Boolean,
      value: false
    }
  },

  data: {
    // 表单数据
    inputWeight: '',
    inputReps: '',
    inputRpe: '',
    inputRemark: '',
    // 是否展开输入框
    showInput: false,
    // 是否提交中
    isSubmitting: false,
    // 当前请求 ID（用于幂等）
    currentRequestId: '',
    // 编辑模式
    editingSetIndex: -1,  // -1 表示不在编辑
    editWeight: '',
    editReps: '',
    editRpe: '',
    editRemark: '',
    isEditing: false
  },

  observers: {
    // 监听 exercise 变化，初始化输入默认值
    'exercise': function(exercise) {
      if (!exercise) return
      // strength 默认重量和次数取目标值
      const isStrength = exercise.itemType !== 'cardio'
      this.setData({
        inputWeight: isStrength ? String(exercise.targetWeight || 0) : '',
        inputReps: isStrength ? String(exercise.targetReps || 12) : ''
      })
    }
  },

  methods: {
    /**
     * 展开/收起输入框
     */
    toggleInput() {
      if (this.data.readonly) return
      this.setData({ showInput: !this.data.showInput })
    },

    /**
     * 输入重量
     */
    onWeightInput(e) {
      this.setData({ inputWeight: e.detail.value })
    },

    /**
     * 输入次数
     */
    onRepsInput(e) {
      this.setData({ inputReps: e.detail.value })
    },

    /**
     * 输入 RPE
     */
    onRpeInput(e) {
      this.setData({ inputRpe: e.detail.value })
    },

    /**
     * 输入备注
     */
    onRemarkInput(e) {
      this.setData({ inputRemark: e.detail.value })
    },

    /**
     * 校验 RPE 输入
     * @returns {boolean} 是否有效
     */
    _validateRpe(rpeValue) {
      // 空值允许提交
      if (rpeValue === '' || rpeValue === undefined || rpeValue === null) {
        return true
      }
      const rpe = parseInt(rpeValue, 10)
      // 必须是 1-10 的整数
      if (isNaN(rpe) || rpe < 1 || rpe > 10 || String(rpe) !== String(rpeValue).trim()) {
        return false
      }
      return true
    },

    /**
     * 校验重量（strength 打卡/编辑时）
     * @returns {Object} { valid, value, error }
     */
    _validateWeight(weightValue, isStrength) {
      // cardio 不需要校验重量
      if (!isStrength) return { valid: true, value: undefined }
      // 空值允许（可选）
      if (weightValue === '' || weightValue === undefined || weightValue === null) {
        return { valid: true, value: undefined }
      }
      const weight = parseFloat(weightValue)
      if (isNaN(weight) || weight < 0 || weight > 1000) {
        return { valid: false, error: '重量必须在 0-1000 之间' }
      }
      return { valid: true, value: weight }
    },

    /**
     * 校验次数（strength 打卡/编辑时）
     * @returns {Object} { valid, value, error }
     */
    _validateReps(repsValue, isStrength) {
      // cardio 不需要校验次数
      if (!isStrength) return { valid: true, value: undefined }
      // 空值允许（可选）
      if (repsValue === '' || repsValue === undefined || repsValue === null) {
        return { valid: true, value: undefined }
      }
      const reps = parseInt(repsValue, 10)
      if (isNaN(reps) || reps < 1 || reps > 999 || String(reps) !== String(repsValue).trim()) {
        return { valid: false, error: '次数必须是 1-999 的整数' }
      }
      return { valid: true, value: reps }
    },

    /**
     * 打卡 +1 组
     */
    async onCheckin() {
      // 防止连续点击
      if (this.data.isSubmitting || this.data.readonly) return

      const { exercise, weekDocId, inputWeight, inputReps, inputRpe, inputRemark } = this.data
      const isStrength = exercise.itemType !== 'cardio'

      // 检查是否已达目标
      if (exercise.completedSets >= exercise.targetSets) {
        wx.showToast({ title: '已完成全部组数', icon: 'none' })
        return
      }

      // 校验重量（strength）
      const weightResult = this._validateWeight(inputWeight, isStrength)
      if (!weightResult.valid) {
        wx.showToast({ title: weightResult.error, icon: 'none' })
        return
      }

      // 校验次数（strength）
      const repsResult = this._validateReps(inputReps, isStrength)
      if (!repsResult.valid) {
        wx.showToast({ title: repsResult.error, icon: 'none' })
        return
      }

      // 校验 RPE
      if (!this._validateRpe(inputRpe)) {
        wx.showToast({ title: 'RPE 必须是 1-10 的整数', icon: 'none' })
        return
      }

      // 生成或复用 requestId（幂等）
      let requestId = this.data.currentRequestId
      if (!requestId) {
        requestId = createTrainingRequestId()
        this.setData({ currentRequestId: requestId })
      }

      this.setData({ isSubmitting: true })

      try {
        const params = {
          weekDocId,
          weekItemId: exercise.weekItemId,
          requestId
        }

        // 使用已校验的值
        if (weightResult.value !== undefined) params.weight = weightResult.value
        if (repsResult.value !== undefined) params.reps = repsResult.value
        const rpe = parseInt(inputRpe, 10)
        if (!isNaN(rpe) && rpe >= 1 && rpe <= 10) params.rpe = rpe
        if (inputRemark.trim()) params.remark = inputRemark.trim()

        const result = await incrementExerciseSet(params)

        // 成功后清除 requestId，准备下一组
        this.setData({
          currentRequestId: '',
          inputRpe: '',
          inputRemark: '',
          showInput: false
        })

        // 通知页面刷新
        this.triggerEvent('checkinSuccess', { result })

        // 显示提示
        if (result.duplicate) {
          wx.showToast({ title: '重复请求，已忽略', icon: 'none' })
        } else {
          wx.showToast({ title: '打卡成功', icon: 'success' })
        }

      } catch (err) {
        console.error('[training-exercise-card] 打卡失败', err)
        
        // 错误处理
        if (err.code === 'TRAINING_TARGET_REACHED') {
          this.setData({ currentRequestId: '' })
          this.triggerEvent('checkinSuccess', {})
        }
        
        wx.showToast({ title: err.message || '打卡失败', icon: 'none' })
      } finally {
        this.setData({ isSubmitting: false })
      }
    },

    /**
     * 开始编辑某组
     */
    onStartEdit(e) {
      if (this.data.readonly || this.data.isEditing) return
      const index = e.currentTarget.dataset.index
      const setDetail = this.data.exercise.setDetails[index]
      if (!setDetail) return

      this.setData({
        editingSetIndex: index,
        editWeight: setDetail.weight !== undefined ? String(setDetail.weight) : '',
        editReps: setDetail.reps !== undefined ? String(setDetail.reps) : '',
        editRpe: setDetail.rpe !== undefined && setDetail.rpe !== null ? String(setDetail.rpe) : '',
        editRemark: setDetail.remark || ''
      })
    },

    /**
     * 取消编辑
     */
    onCancelEdit() {
      this.setData({
        editingSetIndex: -1,
        editWeight: '',
        editReps: '',
        editRpe: '',
        editRemark: ''
      })
    },

    /**
     * 编辑输入
     */
    onEditWeightInput(e) {
      this.setData({ editWeight: e.detail.value })
    },
    onEditRepsInput(e) {
      this.setData({ editReps: e.detail.value })
    },
    onEditRpeInput(e) {
      this.setData({ editRpe: e.detail.value })
    },
    onEditRemarkInput(e) {
      this.setData({ editRemark: e.detail.value })
    },

    /**
     * 保存编辑
     */
    async onSaveEdit() {
      if (this.data.isEditing) return

      const { exercise, weekDocId, editingSetIndex, editWeight, editReps, editRpe, editRemark } = this.data
      const setDetail = exercise.setDetails[editingSetIndex]
      if (!setDetail) return
      const isStrength = exercise.itemType !== 'cardio'

      // 校验重量（strength）
      const weightResult = this._validateWeight(editWeight, isStrength)
      if (!weightResult.valid) {
        wx.showToast({ title: weightResult.error, icon: 'none' })
        return
      }

      // 校验次数（strength）
      const repsResult = this._validateReps(editReps, isStrength)
      if (!repsResult.valid) {
        wx.showToast({ title: repsResult.error, icon: 'none' })
        return
      }

      // 校验 RPE
      if (!this._validateRpe(editRpe)) {
        wx.showToast({ title: 'RPE 必须是 1-10 的整数', icon: 'none' })
        return
      }

      // 校验备注长度
      if (editRemark.length > 200) {
        wx.showToast({ title: '备注不能超过200字符', icon: 'none' })
        return
      }

      this.setData({ isEditing: true })

      try {
        const params = {
          weekDocId,
          weekItemId: exercise.weekItemId,
          requestId: setDetail.requestId
        }

        // 使用已校验的值
        if (weightResult.value !== undefined) params.weight = weightResult.value
        if (repsResult.value !== undefined) params.reps = repsResult.value
        const rpe = parseInt(editRpe, 10)
        if (!isNaN(rpe) && rpe >= 1 && rpe <= 10) {
          params.rpe = rpe
        } else if (editRpe === '' || editRpe === undefined) {
          // 清空 RPE
          params.rpe = null
        }
        params.remark = editRemark.trim()

        await updateExerciseSetDetail(params)

        this.setData({
          editingSetIndex: -1,
          editWeight: '',
          editReps: '',
          editRpe: '',
          editRemark: ''
        })

        // 通知页面刷新
        this.triggerEvent('checkinSuccess', {})
        wx.showToast({ title: '保存成功', icon: 'success' })

      } catch (err) {
        console.error('[training-exercise-card] 编辑失败', err)
        wx.showToast({ title: err.message || '保存失败', icon: 'none' })
      } finally {
        this.setData({ isEditing: false })
      }
    },

    /**
     * 视频操作（打开/复制链接）
     */
    onVideoAction(e) {
      const video = e.currentTarget.dataset.video
      if (!video || !video.url) return

      wx.showActionSheet({
        itemList: ['打开视频', '复制链接'],
        success: (res) => {
          if (res.tapIndex === 0) {
            // 打开视频
            wx.navigateTo({
              url: `/pages/training-webview/training-webview?url=${encodeURIComponent(video.url)}&title=${encodeURIComponent(video.title || '教学视频')}`
            })
          } else if (res.tapIndex === 1) {
            // 复制链接
            wx.setClipboardData({
              data: video.url,
              success: () => {
                wx.showToast({ title: '链接已复制', icon: 'success' })
              }
            })
          }
        }
      })
    }
  }
})
