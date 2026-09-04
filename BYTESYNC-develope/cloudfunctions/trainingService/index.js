// cloudfunctions/trainingService/index.js — 训练功能云函数主入口
// 所有训练相关的 API 请求都通过这个云函数处理

const cloud = require('wx-server-sdk')
const domain = require('./lib/domain')
const validation = require('./lib/validation')

const { TRAINING_ERRORS } = validation

// 初始化云开发
// 本地调试时 DYNAMIC_CURRENT_ENV 可能无法获取，使用 fallback
cloud.init({
  env: cloud.DYNAMIC_CURRENT_ENV || 'cloud1-5gpu3nmc673b62c2'
})

const db = cloud.database()

// ═══════════════════════════════════════════════════════════════
// Action 处理器映射
// ═══════════════════════════════════════════════════════════════

const handlers = {
  // 模板相关
  getTemplate: async (openid, payload) => {
    return domain.getTemplate(db, openid)
  },
  
  createTemplate: async (openid, payload) => {
    return domain.createTemplate(db, openid, payload.days)
  },
  
  updateTemplate: async (openid, payload) => {
    return domain.updateTemplate(db, openid, payload.days)
  },
  
  // 周计划相关
  getOrCreateWeek: async (openid, payload) => {
    return domain.getOrCreateWeek(db, openid, payload.weekId)
  },

  getWeekHistory: async (openid, payload) => {
    return domain.getWeekHistory(db, openid, payload.limit, payload.offset)
  },

  syncCurrentWeek: async (openid, payload) => {
    return domain.syncCurrentWeek(db, openid)
  },
  
  // 打卡相关（使用 weekDocId 和 weekItemId）
  incrementSet: async (openid, payload) => {
    return domain.incrementSet(
      db, 
      openid, 
      payload.weekDocId, 
      payload.weekItemId, 
      {
        requestId: payload.requestId,
        weight: payload.weight,
        reps: payload.reps,
        rpe: payload.rpe,
        remark: payload.remark
      }
    )
  },
  
  updateSetDetail: async (openid, payload) => {
    return domain.updateSetDetail(
      db,
      openid,
      payload.weekDocId,
      payload.weekItemId,
      payload.requestId,
      {
        weight: payload.weight,
        reps: payload.reps,
        rpe: payload.rpe,
        remark: payload.remark
      }
    )
  },
  
  // 自定义动作相关
  getCustomExercises: async (openid, payload) => {
    return domain.getCustomExercises(db, openid)
  },
  
  createCustomExercise: async (openid, payload) => {
    return domain.createCustomExercise(db, openid, {
      name: payload.name,
      englishName: payload.englishName,
      category: payload.category,
      itemType: payload.itemType,
      defaultSets: payload.defaultSets,
      defaultReps: payload.defaultReps,
      defaultWeight: payload.defaultWeight,
      defaultDuration: payload.defaultDuration,
      videoLinks: payload.videoLinks
    })
  },
  
  updateCustomExercise: async (openid, payload) => {
    return domain.updateCustomExercise(db, openid, payload.exerciseId, {
      name: payload.name,
      englishName: payload.englishName,
      category: payload.category,
      itemType: payload.itemType,
      defaultSets: payload.defaultSets,
      defaultReps: payload.defaultReps,
      defaultWeight: payload.defaultWeight,
      defaultDuration: payload.defaultDuration,
      videoLinks: payload.videoLinks
    })
  },
  
  deleteCustomExercise: async (openid, payload) => {
    return domain.deleteCustomExercise(db, openid, payload.exerciseId)
  },
  
  // 视频相关（使用 scopeType）
  addVideo: async (openid, payload) => {
    return domain.addVideo(
      db,
      openid,
      payload.scopeType,
      payload.scopeId,
      { title: payload.title, url: payload.url }
    )
  },
  
  updateVideo: async (openid, payload) => {
    return domain.updateVideo(
      db,
      openid,
      payload.scopeType,
      payload.scopeId,
      payload.videoId,
      { title: payload.title, url: payload.url }
    )
  },
  
  deleteVideo: async (openid, payload) => {
    return domain.deleteVideo(
      db,
      openid,
      payload.scopeType,
      payload.scopeId,
      payload.videoId
    )
  }
}

// ═══════════════════════════════════════════════════════════════
// 云函数入口
// ═══════════════════════════════════════════════════════════════

exports.main = async (event, context) => {
  // 从微信服务端获取 openid，确保安全性
  const wxContext = cloud.getWXContext()
  // 本地调试时 OPENID 为 undefined，使用测试值
  const OPENID = wxContext.OPENID || wxContext.FROM_OPENID || event._testOpenid

  // 调试日志
  console.log('[trainingService] OPENID:', OPENID, '| action:', event?.action)

  if (!OPENID) {
    console.error('[trainingService] OPENID 为空，拒绝访问')
    return {
      success: false,
      error: TRAINING_ERRORS.UNAUTHORIZED
    }
  }
  
  // 读取 action 和 payload
  const action = event && event.action
  const payload = (event && event.payload) || {}
  
  // 检查 action 是否存在
  if (!action || typeof action !== 'string') {
    return {
      success: false,
      error: TRAINING_ERRORS.INVALID_INPUT
    }
  }
  
  // 查找对应的处理器
  const handler = handlers[action]
  
  if (!handler) {
    return {
      success: false,
      error: {
        code: 'TRAINING_UNKNOWN_ACTION',
        message: `未知的操作: ${action}`
      }
    }
  }
  
  try {
    // 执行处理器
    const result = await handler(OPENID, payload)
    return result
  } catch (err) {
    // 在云函数日志中记录错误
    console.error(`[trainingService] ${action} error:`, err)
    
    // 返回客户端时只返回固定信息，禁止泄露内部异常
    return {
      success: false,
      error: {
        code: 'TRAINING_INTERNAL_ERROR',
        message: '服务器内部错误'
      }
    }
  }
}
