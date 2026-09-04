// pages/record/record.js
const { addMeal, addMeals, analyzeMeal, analyzeMealByText, deleteCloudFile, getUsersByPairId, getYesterdayMealsForReuse } = require('../../utils/api')
const { getCurrentDate, getCurrentTime, getYesterdayDate } = require('../../utils/time')

const app = getApp()

Page({
  data: {
    state:          'idle',    // 'idle' | 'loading' | 'result'
    tempImageUrl:   '',
    currentFileID:  '',        // 当前识别使用的云存储 fileID，留作重识别用
    foodData:       null,
    baseFoodData:   null,
    portionRatio:   1,
    aiHint:         '',
    loadingText:    '识别中…',
    loadingSubtext: '正在估算这份料理',
    loadingProgress: 0,
    manualExpanded: false,
    manualForm: { name: '', calories: '', protein: '', carbs: '', fat: '' },
    // 昨天也吃了？（快捷复用模块）
    yesterdayMeals:        [],
    isAddingFromYesterday: false,
    shareMode:    'solo',
    sharePreview: { meCalories: 0, taCalories: 0 },
    // 识别后修改：补充提示词再识别
    refineExpanded: false,
    refineHint:     '',
    // 识别后修改：直接改数据
    editExpanded: false,
    editForm:     { name: '', calories: '', protein: '', carbs: '', fat: '' },
  },

  onHintInput(e) {
    this.setData({ aiHint: e.detail.value })
  },

  // ── 手动记录 ──────────────────────────────
  toggleManualForm() {
    this.setData({ manualExpanded: !this.data.manualExpanded })
  },

  onManualInput(e) {
    const field = e.currentTarget.dataset.field
    this.setData({ [`manualForm.${field}`]: e.detail.value })
  },

  onManualSave() {
    const { name, calories, protein, carbs, fat } = this.data.manualForm
    const cal = Number(calories)
    if (!calories || cal <= 0) {
      wx.showToast({ title: '请填写卡路里', icon: 'none', duration: 1500 })
      return
    }
    const foodData = {
      name:     name.trim() || '手动记录',
      calories: Math.round(cal),
      protein:  Math.round(Number(protein) || 0),
      carbs:    Math.round(Number(carbs)   || 0),
      fat:      Math.round(Number(fat)     || 0),
      imageUrl: '',
      hint:     '',
      source:   'manual',
      dishes:   [],
    }
    this.setData({
      baseFoodData:   foodData,
      foodData:       foodData,
      portionRatio:   1,
      state:          'result',
      manualExpanded: false,
    })
  },
  // ── 共享逻辑辅助 ─────────────────────────────────
  _getShareRatios(mode) {
    const map = { solo: [1, 0], ta_only: [0, 1], half: [0.5, 0.5], me_1_3: [1/3, 2/3], me_2_3: [2/3, 1/3] }
    return map[mode] || [1, 0]
  },

  _calcSharePreview(calories, mode) {
    const [me, ta] = this._getShareRatios(mode)
    return { meCalories: Math.round(calories * me), taCalories: Math.round(calories * ta) }
  },

  // 把 dishes 数组按比例缩放（仅缩放 calories；name 原样保留）
  _scaleDishes(dishes, ratio) {
    if (!Array.isArray(dishes)) return []
    return dishes
      .filter(d => d && d.name)
      .map(d => ({
        name:     String(d.name).slice(0, 20),
        calories: Math.round((Number(d.calories) || 0) * ratio),
      }))
  },

  _buildMeal(ratio, foodData, userId, userName, role, pairId, shareMode, sharedMealId) {
    const cal  = Math.round(foodData.calories * ratio)
    const prot = Math.round(foodData.protein  * ratio)
    const carb = Math.round(foodData.carbs    * ratio)
    const ft   = Math.round(foodData.fat      * ratio)
    // base = 识别/手动录入的原始一人份；portionRatio = 用户选择的份量；ratio = 双人分摊比例
    // 该条目最终占比 = portionRatio × ratio
    const base             = this.data.baseFoodData || foodData
    const baseDishes       = Array.isArray(base.dishes) ? base.dishes : []
    const effectiveRatio   = (Number(this.data.portionRatio) || 1) * ratio
    const baseDishesClean  = this._scaleDishes(baseDishes, 1)
    const dishes           = this._scaleDishes(baseDishes, effectiveRatio)
    return {
      pairId, userId, userName, role,
      name:             foodData.name,
      calories:         cal,
      protein:          prot,
      carbs:            carb,
      fat:              ft,
      // ── original*：该条目写入时的值，summary 页“按比例修改”以此为基线（向后兼容）──
      originalCalories: cal,
      originalProtein:  prot,
      originalCarbs:    carb,
      originalFat:      ft,
      // ── base*：原始一人份识别基准，不受份量/分摊影响，供后续重识别/手动改值使用 ──
      baseCalories:     Math.round(base.calories || 0),
      baseProtein:      Math.round(base.protein  || 0),
      baseCarbs:        Math.round(base.carbs    || 0),
      baseFat:          Math.round(base.fat      || 0),
      // ── 卡路里明细 ──
      dishes,                    // 当前条目实际值
      originalDishes: dishes,    // 与 original* 对齐：summary 按比例缩放时的基线
      baseDishes:     baseDishesClean,  // 原始一人份明细
      imageUrl:         foodData.imageUrl  || '',
      hint:             foodData.hint      || '',
      source:           foodData.source    || 'ai',
      portionRatio:     this.data.portionRatio,
      shareRatio:       ratio,
      shareMode,
      sharedMealId:     sharedMealId || '',
      date:             getCurrentDate(),
      time:             getCurrentTime(),
      createdAt:        new Date(),
    }
  },

  onShareModeChange(e) {
    const clicked = e.currentTarget.dataset.mode
    let newMode
    if (clicked === 'solo') {
      newMode = 'solo'
    } else if (clicked === 'ta_only') {
      newMode = 'ta_only'
    } else {
      // clicked === 'shared'：一起吃
      newMode = (this.data.shareMode === 'solo' || this.data.shareMode === 'ta_only') ? 'half' : this.data.shareMode
    }
    const cal = (this.data.foodData && this.data.foodData.calories) || 0
    this.setData({ shareMode: newMode, sharePreview: this._calcSharePreview(cal, newMode) })
  },

  onSplitTap(e) {
    const mode = e.currentTarget.dataset.mode
    const cal  = (this.data.foodData && this.data.foodData.calories) || 0
    this.setData({ shareMode: mode, sharePreview: this._calcSharePreview(cal, mode) })
  },
  // 配对守卫：未配对则跳转 pairing
  onShow() {
    app._initPromise.then(() => {
      if (!app.globalData.pairId) {
        wx.redirectTo({ url: '/pages/pairing/pairing' })
        return
      }
      this._loadYesterdayMeals()
    })
  },

  /**
   * 加载昨天的餐食记录（仅当前用户，最多 3 条），用于「昨天也吃了？」快捷复用
   */
  _loadYesterdayMeals() {
    const { pairId, openid } = app.globalData
    if (!pairId || !openid) return

    const yesterdayStr = getYesterdayDate()
    getYesterdayMealsForReuse(yesterdayStr, pairId, openid)
      .then(res => {
        const meals = (res.data || []).map(m => ({
          id:       m._id,
          name:     m.name || '记录',
          calories: m.calories || 0,
          protein:  m.protein  || 0,
          carbs:    m.carbs    || 0,
          fat:      m.fat      || 0,
        }))
        this.setData({ yesterdayMeals: meals })
      })
      .catch(err => {
        console.warn('[record] 加载昨天餐食失败', err)
        this.setData({ yesterdayMeals: [] })
      })
  },

  /**
   * 点击「添加」：把昨天这条餐食填入手动记录表单，展开表单供用户确认/修改后再保存
   */
  onAddYesterdayMeal(e) {
    if (this.data.isAddingFromYesterday) return

    const idx  = e.currentTarget.dataset.idx
    const meal = this.data.yesterdayMeals[idx]
    if (!meal) return

    this.setData({
      isAddingFromYesterday: true,
      manualExpanded: true,
      manualForm: {
        name:     meal.name || '',
        calories: meal.calories ? String(meal.calories) : '',
        protein:  meal.protein  ? String(meal.protein)  : '',
        carbs:    meal.carbs    ? String(meal.carbs)    : '',
        fat:      meal.fat      ? String(meal.fat)      : '',
      },
    })
    wx.showToast({ title: '已填入昨天的记录，可修改后保存', icon: 'none', duration: 1500 })
    this.setData({ isAddingFromYesterday: false })
  },

  // 文字描述直接识别
  onTextAnalyze() {
    const hint = (this.data.aiHint || '').trim()
    if (!hint) {
      wx.showToast({ title: '请输入食物描述', icon: 'none', duration: 1500 })
      return
    }
    this.setData({
      state:          'loading',
      tempImageUrl:   '',
      loadingText:    '查询中…',
      loadingSubtext: '正在估算这份料理',
      loadingProgress: 60,
    })
    analyzeMealByText(hint)
      .then(result => {
        if (!result.success) throw new Error(result.error || '查询失败')
        const originalFoodData = {
          name:            result.name,
          calories:        result.calories,
          protein:         result.protein,
          carbs:           result.carbs,
          fat:             result.fat,
          dishes:          Array.isArray(result.dishes) ? result.dishes : [],
          imageUrl:        '',
          previewImageUrl: '',
          hint,
          source:          'text',
        }
        this.setData({ baseFoodData: originalFoodData, foodData: originalFoodData, portionRatio: 1, state: 'result' })
      })
      .catch(err => {
        console.error('[record] 文字识别失败', err)
        wx.showToast({ title: '查询失败，请重试', icon: 'none', duration: 2000 })
        this.setData({ state: 'idle' })
      })
  },

  // 点击拍照按钮
  onCameraTap() {
    wx.chooseMedia({
      count: 1,
      mediaType: ['image'],
      sourceType: ['album', 'camera'],
      sizeType: ['compressed'],   // 系统层面压缩，大幅减小体积
      success: (res) => {
        const tempFilePath = res.tempFiles[0].tempFilePath
        this.setData({
          tempImageUrl:   tempFilePath,
          state:          'loading',
          loadingText:    '上传中…',
          loadingSubtext: '正在上传图片',
          loadingProgress: 30,
        })
        this._analyze(tempFilePath)
      },
      fail: () => {},
    })
  },

  // 上传 + AI 识别
  _analyze(tempFilePath) {
    // 双重压缩：sizeType 已做系统压缩，这里再降 quality 减小体积
    wx.compressImage({
      src:     tempFilePath,
      quality: 40,
      success: ({ tempFilePath: compressed }) => this._upload(compressed),
      fail:    ()                            => this._upload(tempFilePath),
    })
  },

  _upload(filePath) {
    const cloudPath = `meals/${Date.now()}.jpg`
    console.log('[record] uploading to', cloudPath)

    wx.cloud.uploadFile({
      cloudPath,
      filePath,
      success: (uploadRes) => {
        const fileID = uploadRes.fileID
        console.log('[record] upload ok', fileID)

        // 阶段 2：调用 AI 云函数
        this.setData({
          loadingText:    '识别中…',
          loadingSubtext: '正在估算这份料理',
          loadingProgress: 75,
        })

        analyzeMeal(fileID, this.data.aiHint)
          .then(result => {
            if (!result.success) {
              throw new Error(result.error || 'AI 识别失败')
            }
            // fileID 保留到 data，供"补充说明再次识别"复用；保存/重拍/页面销毁时再清理
            const originalFoodData = {
              name:            result.name,
              calories:        result.calories,
              protein:         result.protein,
              carbs:           result.carbs,
              fat:             result.fat,
              dishes:          Array.isArray(result.dishes) ? result.dishes : [],
              imageUrl:        '',
              previewImageUrl: this.data.tempImageUrl,
              hint:            this.data.aiHint,
              source:          'ai',
            }
            this.setData({
              baseFoodData:  originalFoodData,
              foodData:      originalFoodData,
              portionRatio:  1,
              currentFileID: fileID,
              state:         'result',
            })
          })
          .catch(err => {
            // 识别失败时清理临时文件
            deleteCloudFile(fileID).catch(e => console.warn('[record] 删除临时图片失败', e))
            console.error('[record] AI 识别失败', err)
            wx.showToast({ title: '识别失败，请重试', icon: 'none', duration: 2000 })
            this.setData({ state: 'idle' })
          })
      },
      fail: (err) => {
        console.error('[record] 上传失败', JSON.stringify(err))
        wx.showToast({ title: '上传失败，请重试', icon: 'none', duration: 2000 })
        this.setData({ state: 'idle', tempImageUrl: '' })
      },
    })
  },

  // 快捷比例调整
  onRatioTap(e) {
    const base  = this.data.baseFoodData
    const ratio = Number(e.currentTarget.dataset.ratio)
    const newFoodData = {
      ...base,
      calories: Math.round(base.calories * ratio),
      protein:  Math.round(base.protein  * ratio),
      carbs:    Math.round(base.carbs    * ratio),
      fat:      Math.round(base.fat      * ratio),
      dishes:   this._scaleDishes(base.dishes, ratio),
    }
    this.setData({
      portionRatio: ratio,
      foodData:     newFoodData,
      sharePreview: this._calcSharePreview(newFoodData.calories, this.data.shareMode),
    })
  },

  // ── 识别后修改：补充说明再次识别 ─────────────────
  onRefineToggle() {
    this.setData({
      refineExpanded: !this.data.refineExpanded,
      editExpanded:   false,
      refineHint:     '',
    })
  },

  onRefineHintInput(e) {
    this.setData({ refineHint: e.detail.value })
  },

  onRefineAnalyze() {
    const extra = (this.data.refineHint || '').trim()
    if (!extra) {
      wx.showToast({ title: '请输入补充说明', icon: 'none', duration: 1500 })
      return
    }
    const base       = this.data.baseFoodData || {}
    const prevHint   = (base.hint || '').trim()
    const mergedHint = prevHint ? `${prevHint}；${extra}` : extra
    const fileID     = this.data.currentFileID
    const isImage    = base.source !== 'text' && base.source !== 'manual' && !!fileID

    this.setData({
      state:          'loading',
      loadingText:    '重新识别中…',
      loadingSubtext: '正在按你的补充重新估算',
      loadingProgress: 65,
    })

    const task = isImage
      ? analyzeMeal(fileID, mergedHint)
      : analyzeMealByText(mergedHint)

    task
      .then(result => {
        if (!result.success) throw new Error(result.error || '重新识别失败')
        const newFoodData = {
          name:            result.name,
          calories:        result.calories,
          protein:         result.protein,
          carbs:           result.carbs,
          fat:             result.fat,
          dishes:          Array.isArray(result.dishes) ? result.dishes : [],
          imageUrl:        base.imageUrl        || '',
          previewImageUrl: base.previewImageUrl || '',
          hint:            mergedHint,
          source:          base.source || (isImage ? 'ai' : 'text'),
        }
        this.setData({
          baseFoodData:   newFoodData,
          foodData:       newFoodData,
          portionRatio:   1,
          refineExpanded: false,
          refineHint:     '',
          state:          'result',
          sharePreview:   this._calcSharePreview(newFoodData.calories, this.data.shareMode),
        })
        wx.showToast({ title: '已更新', icon: 'success', duration: 1000 })
      })
      .catch(err => {
        console.error('[record] 重新识别失败', err)
        wx.showToast({ title: '重新识别失败，请再试', icon: 'none', duration: 2000 })
        this.setData({ state: 'result' })
      })
  },

  // ── 识别后修改：直接改卡路里/宏量 ─────────────────
  onEditToggle() {
    const f = this.data.foodData || {}
    this.setData({
      editExpanded:   !this.data.editExpanded,
      refineExpanded: false,
      editForm: {
        name:     f.name || '',
        calories: String(f.calories || 0),
        protein:  String(f.protein  || 0),
        carbs:    String(f.carbs    || 0),
        fat:      String(f.fat      || 0),
      },
    })
  },

  onEditInput(e) {
    const field = e.currentTarget.dataset.field
    this.setData({ [`editForm.${field}`]: e.detail.value })
  },

  onEditSave() {
    const { name, calories, protein, carbs, fat } = this.data.editForm
    const cal = Number(calories)
    if (!cal || cal <= 0) {
      wx.showToast({ title: '卡路里需大于 0', icon: 'none', duration: 1500 })
      return
    }
    const base = this.data.baseFoodData || {}
    const prev = this.data.foodData     || {}
    // 用户直接改了数值；保留 dishes 仅作明细参考，不再强制联动
    const newFoodData = {
      ...prev,
      name:     (name || prev.name || '手动记录').trim(),
      calories: Math.round(cal),
      protein:  Math.round(Number(protein) || 0),
      carbs:    Math.round(Number(carbs)   || 0),
      fat:      Math.round(Number(fat)     || 0),
    }
    // base 也同步更新成新的"一人份"基准，后续份量缩放从新值出发
    const newBase = {
      ...base,
      name:     newFoodData.name,
      calories: newFoodData.calories,
      protein:  newFoodData.protein,
      carbs:    newFoodData.carbs,
      fat:      newFoodData.fat,
    }
    this.setData({
      baseFoodData: newBase,
      foodData:     newFoodData,
      portionRatio: 1,
      editExpanded: false,
      sharePreview: this._calcSharePreview(newFoodData.calories, this.data.shareMode),
    })
    wx.showToast({ title: '已更新', icon: 'success', duration: 1000 })
  },

  // 清理云存储临时图片（识别成功后挂在 data 上）
  _cleanupFileID() {
    const fileID = this.data.currentFileID
    if (!fileID) return
    deleteCloudFile(fileID).catch(err => console.warn('[record] 删除临时图片失败', err))
    this.setData({ currentFileID: '' })
  },

  onUnload() {
    this._cleanupFileID()
  },

  // 记录这一餐 → 写入云数据库 meals collection
  onSave() {
    const { foodData, shareMode } = this.data
    const { openid, userProfile, pairId } = app.globalData

    if (!openid || !userProfile || !pairId) {
      console.warn('[record] globalData not ready', { openid, userProfile, pairId })
      wx.showToast({ title: '初始化未完成，请稍后重试', icon: 'none', duration: 2000 })
      return
    }

    wx.showLoading({ title: '保存中…', mask: true })

    const [meRatio, taRatio] = this._getShareRatios(shareMode)
    const sharedMealId = (shareMode !== 'solo' && shareMode !== 'ta_only') ? 'shared_' + Date.now() : ''

    // 根据 shareMode 决定保存逻辑
    let doSave
    if (shareMode === 'solo') {
      // 只给自己记
      const myMeal = this._buildMeal(meRatio, foodData, openid, userProfile.userName, userProfile.role, pairId, shareMode, '')
      doSave = addMeal(myMeal)
    } else if (shareMode === 'ta_only') {
      // 只给 Ta 记
      doSave = getUsersByPairId(pairId).then(res => {
        const ta = (res.data || []).find(u => u.openid !== openid)
        if (!ta) throw new Error('找不到配对用户')
        const taMeal = this._buildMeal(taRatio, foodData, ta.openid, ta.userName, ta.role, pairId, shareMode, '')
        return addMeal(taMeal)
      })
    } else {
      // 一起吃：两个人各记一条
      const myMeal = this._buildMeal(meRatio, foodData, openid, userProfile.userName, userProfile.role, pairId, shareMode, sharedMealId)
      doSave = getUsersByPairId(pairId).then(res => {
        const ta = (res.data || []).find(u => u.openid !== openid)
        if (!ta) throw new Error('找不到配对用户')
        const taMeal = this._buildMeal(taRatio, foodData, ta.openid, ta.userName, ta.role, pairId, shareMode, sharedMealId)
        return addMeals([myMeal, taMeal])
      })
    }

    doSave
      .then(() => {
        wx.hideLoading()
        wx.showToast({ title: '已记录', icon: 'success', duration: 1200 })
        this._cleanupFileID()
        setTimeout(() => {
          this.setData({
            state: 'idle', tempImageUrl: '', foodData: null,
            baseFoodData: null, portionRatio: 1, aiHint: '',
            shareMode: 'solo', sharePreview: { meCalories: 0, taCalories: 0 },
            manualExpanded: false,
            manualForm: { name: '', calories: '', protein: '', carbs: '', fat: '' },
            refineExpanded: false, refineHint: '',
            editExpanded: false,
            editForm: { name: '', calories: '', protein: '', carbs: '', fat: '' },
          })
        }, 1200)
      })
      .catch((err) => {
        wx.hideLoading()
        console.error('[record] 保存失败', err)
        wx.showToast({ title: '保存失败，请重试', icon: 'none', duration: 2000 })
      })
  },

  // 重新拍摄（保留 aiHint，用户可能只是照片拍错了）
  onRetake() {
    this._cleanupFileID()
    this.setData({
      state: 'idle', tempImageUrl: '', foodData: null,
      baseFoodData: null, portionRatio: 1,
      shareMode: 'solo', sharePreview: { meCalories: 0, taCalories: 0 },
      manualExpanded: false,
      manualForm: { name: '', calories: '', protein: '', carbs: '', fat: '' },
      refineExpanded: false, refineHint: '',
      editExpanded: false,
      editForm: { name: '', calories: '', protein: '', carbs: '', fat: '' },
    })
    this.onCameraTap()
  },
})
