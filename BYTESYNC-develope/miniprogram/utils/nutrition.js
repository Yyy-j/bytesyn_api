// utils/nutrition.js — 营养素计算工具

/** 每克宏量营养素对应热量（kcal） */
const CALORIE_PER_GRAM = {
  protein: 4,
  carbs: 4,
  fat: 9
}

/**
 * 根据三大宏量营养素计算总热量（kcal）
 */
const calcCalories = ({ protein = 0, carbs = 0, fat = 0 }) =>
  Math.round(
    protein * CALORIE_PER_GRAM.protein +
    carbs   * CALORIE_PER_GRAM.carbs   +
    fat     * CALORIE_PER_GRAM.fat
  )

/**
 * 计算某营养素完成度百分比（0～100，不超过 100）
 */
const calcPct = (val, goal) => {
  if (!goal) return 0
  return Math.min(100, Math.round((val / goal) * 100))
}

/** 默认每日目标（后续可改为用户个人配置） */
const DEFAULT_GOALS = {
  calories: 2000,
  protein: 60,
  carbs: 250,
  fat: 65
}

module.exports = { calcCalories, calcPct, DEFAULT_GOALS, CALORIE_PER_GRAM }
