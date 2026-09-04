// utils/training-exercises.js — 固定训练动作库
// 本文件定义了系统内置的 27 个标准训练动作
// 所有动作默认不包含教学视频，由用户自行添加

/**
 * 动作分类列表
 * 用于页面筛选和动作选择器
 */
const CATEGORIES = [
  '胸部',
  '背部',
  '肩部前束',
  '肩部中束',
  '肩部后束',
  '肱二头',
  '肱三头',
  '腿部',
  '核心',
  '肩袖/体态'
]

/**
 * 固定动作库
 * 每个动作包含：
 * - id: 稳定的唯一标识，使用英文小写和下划线
 * - name: 中文名称
 * - englishName: 英文名称（用于搜索和显示）
 * - category: 所属分类
 * - sourceType: 固定为 "fixed" 表示系统内置
 * - itemType: 动作类型，"strength"（力量）或 "cardio"（有氧/时长类）
 * - defaultSets: 默认组数
 * - defaultReps: 默认每组次数
 * - defaultWeight: 默认重量（千克）
 * - defaultDuration: 默认时长（秒），仅有氧/静态动作使用
 * - videoLinks: 教学视频链接数组，默认为空
 */
const FIXED_EXERCISES = [
  // ═══════════════════════════════════════════════════════
  // 胸部 (3个动作)
  // ═══════════════════════════════════════════════════════
  {
    id: 'chest_press',
    name: '器械胸推',
    englishName: 'Chest Press',
    category: '胸部',
    sourceType: 'fixed',
    itemType: 'strength',
    defaultSets: 4,
    defaultReps: 12,
    defaultWeight: 20,
    defaultDuration: 0,
    videoLinks: []
  },
  {
    id: 'incline_dumbbell_press',
    name: '上斜哑铃卧推',
    englishName: 'Incline Dumbbell Press',
    category: '胸部',
    sourceType: 'fixed',
    itemType: 'strength',
    defaultSets: 4,
    defaultReps: 10,
    defaultWeight: 12,
    defaultDuration: 0,
    videoLinks: []
  },
  {
    id: 'incline_press',
    name: '上斜推胸',
    englishName: 'Incline Press',
    category: '胸部',
    sourceType: 'fixed',
    itemType: 'strength',
    defaultSets: 4,
    defaultReps: 12,
    defaultWeight: 15,
    defaultDuration: 0,
    videoLinks: []
  },

  // ═══════════════════════════════════════════════════════
  // 背部 (5个动作)
  // ═══════════════════════════════════════════════════════
  {
    id: 'front_lat_pulldown',
    name: '前置高位下拉',
    englishName: 'Front Lat Pulldown',
    category: '背部',
    sourceType: 'fixed',
    itemType: 'strength',
    defaultSets: 4,
    defaultReps: 12,
    defaultWeight: 30,
    defaultDuration: 0,
    videoLinks: []
  },
  {
    id: 'neutral_grip_pulldown',
    name: '中立握高位下拉',
    englishName: 'Neutral Grip Lat Pulldown',
    category: '背部',
    sourceType: 'fixed',
    itemType: 'strength',
    defaultSets: 4,
    defaultReps: 12,
    defaultWeight: 30,
    defaultDuration: 0,
    videoLinks: []
  },
  {
    id: 'seated_row',
    name: '坐姿划船',
    englishName: 'Seated Row',
    category: '背部',
    sourceType: 'fixed',
    itemType: 'strength',
    defaultSets: 4,
    defaultReps: 12,
    defaultWeight: 35,
    defaultDuration: 0,
    videoLinks: []
  },
  {
    id: 'chest_supported_tbar_row',
    name: '胸托T-Bar划船',
    englishName: 'Chest Supported T-Bar Row',
    category: '背部',
    sourceType: 'fixed',
    itemType: 'strength',
    defaultSets: 4,
    defaultReps: 10,
    defaultWeight: 20,
    defaultDuration: 0,
    videoLinks: []
  },
  {
    id: 'low_row',
    name: 'Low Row',
    englishName: 'Low Row',
    category: '背部',
    sourceType: 'fixed',
    itemType: 'strength',
    defaultSets: 4,
    defaultReps: 12,
    defaultWeight: 30,
    defaultDuration: 0,
    videoLinks: []
  },

  // ═══════════════════════════════════════════════════════
  // 肩部前束 (1个动作)
  // ═══════════════════════════════════════════════════════
  {
    id: 'shoulder_press',
    name: '器械肩推',
    englishName: 'Shoulder Press',
    category: '肩部前束',
    sourceType: 'fixed',
    itemType: 'strength',
    defaultSets: 4,
    defaultReps: 12,
    defaultWeight: 15,
    defaultDuration: 0,
    videoLinks: []
  },

  // ═══════════════════════════════════════════════════════
  // 肩部中束 (3个动作)
  // ═══════════════════════════════════════════════════════
  {
    id: 'lateral_raise',
    name: '侧平举',
    englishName: 'Lateral Raise',
    category: '肩部中束',
    sourceType: 'fixed',
    itemType: 'strength',
    defaultSets: 4,
    defaultReps: 15,
    defaultWeight: 5,
    defaultDuration: 0,
    videoLinks: []
  },
  {
    id: 'side_lying_lateral_raise',
    name: '侧卧哑铃侧平举',
    englishName: 'Side Lying Dumbbell Lateral Raise',
    category: '肩部中束',
    sourceType: 'fixed',
    itemType: 'strength',
    defaultSets: 3,
    defaultReps: 12,
    defaultWeight: 3,
    defaultDuration: 0,
    videoLinks: []
  },
  {
    id: 'lateral_raise_machine',
    name: '专用侧平举机',
    englishName: 'Lateral Raise Machine',
    category: '肩部中束',
    sourceType: 'fixed',
    itemType: 'strength',
    defaultSets: 4,
    defaultReps: 15,
    defaultWeight: 10,
    defaultDuration: 0,
    videoLinks: []
  },

  // ═══════════════════════════════════════════════════════
  // 肩部后束 (2个动作)
  // ═══════════════════════════════════════════════════════
  {
    id: 'reverse_pec_deck',
    name: '反向蝴蝶机',
    englishName: 'Reverse Pec Deck',
    category: '肩部后束',
    sourceType: 'fixed',
    itemType: 'strength',
    defaultSets: 4,
    defaultReps: 15,
    defaultWeight: 15,
    defaultDuration: 0,
    videoLinks: []
  },
  {
    id: 'prone_y_raise',
    name: '俯卧Y举',
    englishName: 'Prone Y Raise',
    category: '肩部后束',
    sourceType: 'fixed',
    itemType: 'strength',
    defaultSets: 3,
    defaultReps: 12,
    defaultWeight: 2,
    defaultDuration: 0,
    videoLinks: []
  },

  // ═══════════════════════════════════════════════════════
  // 肱二头 (2个动作)
  // ═══════════════════════════════════════════════════════
  {
    id: 'dumbbell_curl',
    name: '哑铃弯举',
    englishName: 'Dumbbell Curl',
    category: '肱二头',
    sourceType: 'fixed',
    itemType: 'strength',
    defaultSets: 3,
    defaultReps: 12,
    defaultWeight: 8,
    defaultDuration: 0,
    videoLinks: []
  },
  {
    id: 'cable_curl',
    name: '绳索弯举',
    englishName: 'Cable Curl',
    category: '肱二头',
    sourceType: 'fixed',
    itemType: 'strength',
    defaultSets: 3,
    defaultReps: 12,
    defaultWeight: 10,
    defaultDuration: 0,
    videoLinks: []
  },

  // ═══════════════════════════════════════════════════════
  // 肱三头 (1个动作)
  // ═══════════════════════════════════════════════════════
  {
    id: 'cable_pushdown',
    name: '绳索下压',
    englishName: 'Cable Pushdown',
    category: '肱三头',
    sourceType: 'fixed',
    itemType: 'strength',
    defaultSets: 3,
    defaultReps: 12,
    defaultWeight: 15,
    defaultDuration: 0,
    videoLinks: []
  },

  // ═══════════════════════════════════════════════════════
  // 腿部 (4个动作)
  // ═══════════════════════════════════════════════════════
  {
    id: 'seated_leg_curl',
    name: '坐姿腿弯举',
    englishName: 'Seated Leg Curl',
    category: '腿部',
    sourceType: 'fixed',
    itemType: 'strength',
    defaultSets: 4,
    defaultReps: 12,
    defaultWeight: 25,
    defaultDuration: 0,
    videoLinks: []
  },
  {
    id: 'leg_press',
    name: '腿举',
    englishName: 'Leg Press',
    category: '腿部',
    sourceType: 'fixed',
    itemType: 'strength',
    defaultSets: 4,
    defaultReps: 12,
    defaultWeight: 80,
    defaultDuration: 0,
    videoLinks: []
  },
  {
    id: 'high_bench_sit_to_stand',
    name: '高凳坐站',
    englishName: 'High Bench Sit to Stand',
    category: '腿部',
    sourceType: 'fixed',
    itemType: 'strength',
    defaultSets: 3,
    defaultReps: 15,
    defaultWeight: 0,
    defaultDuration: 0,
    videoLinks: []
  },
  {
    id: 'light_leg_press',
    name: '轻重量腿举',
    englishName: 'Light Leg Press',
    category: '腿部',
    sourceType: 'fixed',
    itemType: 'strength',
    defaultSets: 3,
    defaultReps: 20,
    defaultWeight: 40,
    defaultDuration: 0,
    videoLinks: []
  },

  // ═══════════════════════════════════════════════════════
  // 核心 (4个动作)
  // ═══════════════════════════════════════════════════════
  {
    id: 'cable_crunch',
    name: '绳索卷腹',
    englishName: 'Cable Crunch',
    category: '核心',
    sourceType: 'fixed',
    itemType: 'strength',
    defaultSets: 3,
    defaultReps: 15,
    defaultWeight: 20,
    defaultDuration: 0,
    videoLinks: []
  },
  {
    id: 'pallof_press',
    name: 'Pallof Press',
    englishName: 'Pallof Press',
    category: '核心',
    sourceType: 'fixed',
    itemType: 'strength',
    defaultSets: 3,
    defaultReps: 10,
    defaultWeight: 10,
    defaultDuration: 0,
    videoLinks: []
  },
  {
    id: 'side_plank',
    name: '侧桥',
    englishName: 'Side Plank',
    category: '核心',
    sourceType: 'fixed',
    itemType: 'cardio',  // 静态保持，使用时长
    defaultSets: 3,
    defaultReps: 1,
    defaultWeight: 0,
    defaultDuration: 30,  // 30秒
    videoLinks: []
  },
  {
    id: 'dead_bug',
    name: 'Dead Bug',
    englishName: 'Dead Bug',
    category: '核心',
    sourceType: 'fixed',
    itemType: 'strength',
    defaultSets: 3,
    defaultReps: 10,
    defaultWeight: 0,
    defaultDuration: 0,
    videoLinks: []
  },

  // ═══════════════════════════════════════════════════════
  // 肩袖/体态 (2个动作)
  // ═══════════════════════════════════════════════════════
  {
    id: 'cable_external_rotation',
    name: '绳索外旋',
    englishName: 'Cable External Rotation',
    category: '肩袖/体态',
    sourceType: 'fixed',
    itemType: 'strength',
    defaultSets: 3,
    defaultReps: 15,
    defaultWeight: 5,
    defaultDuration: 0,
    videoLinks: []
  },
  {
    id: 'scapular_control',
    name: '肩胛控制训练',
    englishName: 'Scapular Control Exercise',
    category: '肩袖/体态',
    sourceType: 'fixed',
    itemType: 'strength',
    defaultSets: 3,
    defaultReps: 12,
    defaultWeight: 0,
    defaultDuration: 0,
    videoLinks: []
  }
]

// ═══════════════════════════════════════════════════════════════
// 查询方法
// ═══════════════════════════════════════════════════════════════

/**
 * 根据动作 ID 查找固定动作
 * @param {string} id - 动作 ID
 * @returns {Object|null} 动作对象，未找到返回 null
 */
const getExerciseById = (id) => {
  if (!id || typeof id !== 'string') {
    return null
  }
  return FIXED_EXERCISES.find(ex => ex.id === id) || null
}

/**
 * 根据分类获取动作列表
 * @param {string} category - 分类名称
 * @returns {Array} 该分类下的动作数组
 */
const getExercisesByCategory = (category) => {
  if (!category || typeof category !== 'string') {
    return []
  }
  return FIXED_EXERCISES.filter(ex => ex.category === category)
}

/**
 * 根据关键词搜索动作
 * 搜索范围包括：中文名称、英文名称
 * @param {string} keyword - 搜索关键词
 * @returns {Array} 匹配的动作数组
 */
const searchExercises = (keyword) => {
  if (!keyword || typeof keyword !== 'string') {
    return []
  }
  // 转换为小写进行不区分大小写的匹配
  const lowerKeyword = keyword.toLowerCase().trim()
  if (!lowerKeyword) {
    return []
  }
  
  return FIXED_EXERCISES.filter(ex => {
    const nameMatch = ex.name.toLowerCase().includes(lowerKeyword)
    const englishMatch = ex.englishName.toLowerCase().includes(lowerKeyword)
    return nameMatch || englishMatch
  })
}

/**
 * 获取所有固定动作列表
 * @returns {Array} 完整的固定动作数组（深拷贝）
 */
const getAllExercises = () => {
  // 返回深拷贝，避免外部修改影响原数据
  return JSON.parse(JSON.stringify(FIXED_EXERCISES))
}

/**
 * 获取所有分类列表
 * @returns {Array} 分类名称数组
 */
const getAllCategories = () => {
  return [...CATEGORIES]
}

/**
 * 检查是否为有效的固定动作 ID
 * @param {string} id - 动作 ID
 * @returns {boolean} 是否存在
 */
const isValidFixedExerciseId = (id) => {
  return FIXED_EXERCISES.some(ex => ex.id === id)
}

// 导出模块
module.exports = {
  // 常量
  CATEGORIES,
  FIXED_EXERCISES,
  
  // 查询方法
  getExerciseById,
  getExercisesByCategory,
  searchExercises,
  getAllExercises,
  getAllCategories,
  isValidFixedExerciseId
}
