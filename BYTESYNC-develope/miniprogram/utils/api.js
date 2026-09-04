// utils/api.js — 数据库操作封装

// ── Meals ─────────────────────────────────────────────

const addMeal = (mealData) => {
  const db = wx.cloud.database()
  return db.collection('meals').add({ data: mealData })
}

const addMeals = (mealList) => Promise.all(mealList.map(addMeal))

const getMealsByDate = (dateStr, pairId) => {
  const db = wx.cloud.database()
  return db.collection('meals')
    .where({ date: dateStr, pairId })
    .orderBy('time', 'asc')
    .limit(100)
    .get()
}

// 「昨天也吃了？」复用模块专用：只查当前用户自己昨天的记录，最多 3 条
const getYesterdayMealsForReuse = (dateStr, pairId, openid) => {
  const db = wx.cloud.database()
  return db.collection('meals')
    .where({ date: dateStr, pairId, userId: openid })
    .orderBy('time', 'desc')
    .limit(3)
    .get()
}

// ── Users ─────────────────────────────────────────────

const getUserByOpenId = (openid) => {
  const db = wx.cloud.database()
  return db.collection('users').where({ openid }).limit(1).get()
}

const getUsersByPairId = (pairId) => {
  const db = wx.cloud.database()
  return db.collection('users').where({ pairId }).get()
}

const createUser = ({ openid, role, userName, pairId }) => {
  const db = wx.cloud.database()
  const now = new Date()
  return db.collection('users').add({
    data: { openid, role, userName, pairId, createdAt: now, updatedAt: now },
  })
}

const updateUserPair = ({ openid, pairId, role, userName }) => {
  const db = wx.cloud.database()
  return db.collection('users').where({ openid }).update({
    data: { pairId, role, userName, updatedAt: new Date() },
  })
}

// ── Pairs ─────────────────────────────────────────────

const createPair = ({ creatorOpenId }) => {
  const db = wx.cloud.database()
  const pairId = 'pair_' + Date.now()
  const inviteCode = String(Math.floor(100000 + Math.random() * 900000))
  const now = new Date()
  return db.collection('pairs').add({
    data: {
      pairId,
      inviteCode,
      members:   [creatorOpenId],
      createdBy: creatorOpenId,
      createdAt: now,
      updatedAt: now,
    },
  }).then(() => ({ pairId, inviteCode }))
}

const getPairByInviteCode = (inviteCode) => {
  const db = wx.cloud.database()
  return db.collection('pairs').where({ inviteCode }).limit(1).get()
}

const getPairByPairId = (pairId) => {
  const db = wx.cloud.database()
  return db.collection('pairs').where({ pairId }).limit(1).get()
}

const joinPair = ({ openid, inviteCode }) => {
  const db = wx.cloud.database()
  return db.collection('pairs').where({ inviteCode }).limit(1).get()
    .then(res => {
      if (!res.data || res.data.length === 0) {
        return Promise.reject(new Error('邀请码无效'))
      }
      const pair = res.data[0]
      // 已在配对中，直接返回
      if (pair.members && pair.members.includes(openid)) {
        return { pairId: pair.pairId }
      }
      if (pair.members && pair.members.length >= 2) {
        return Promise.reject(new Error('配对已满'))
      }
      const newMembers = [...(pair.members || []), openid]
      return db.collection('pairs').doc(pair._id).update({
        data: { members: newMembers, updatedAt: new Date() },
      }).then(() => ({ pairId: pair.pairId }))
    })
}

// ── Cloud Functions ────────────────────────────────────

const getOpenId = () =>
  wx.cloud.callFunction({ name: 'getOpenId' }).then(res => res.result)

const callCloudFunction = (name, data = {}) => {
  return new Promise((resolve, reject) => {
    wx.cloud.callFunction({
      name,
      data,
      success: res => resolve(res.result),
      fail:    err => reject(err),
    })
  })
}

const analyzeMeal = (fileID, hint = '') => callCloudFunction('analyzeMeal', { fileID, hint, mode: 'image' })

const analyzeMealByText = (text) => callCloudFunction('analyzeMeal', { text, mode: 'text' })

const deleteMeal = (mealId) => {
  const db = wx.cloud.database()
  return db.collection('meals').doc(mealId).remove()
}

const updateMeal = (mealId, data) => {
  const db = wx.cloud.database()
  return db.collection('meals').doc(mealId).update({ data: { ...data, updatedAt: new Date() } })
}

const deleteCloudFile = (fileID) => {
  return new Promise((resolve, reject) => {
    wx.cloud.deleteFile({
      fileList: [fileID],
      success: resolve,
      fail:    reject,
    })
  })
}

const updateUserGoals = ({ openid, goals }) => {
  const db = wx.cloud.database()
  return db.collection('users').where({ openid }).update({
    data: { goals, updatedAt: new Date() },
  })
}

module.exports = {
  // meals
  addMeal, addMeals, getMealsByDate, getYesterdayMealsForReuse, updateMeal,
  // users
  getUserByOpenId, getUsersByPairId, createUser, updateUserPair, updateUserGoals,
  // pairs
  createPair, getPairByInviteCode, getPairByPairId, joinPair,
  // cloud
  getOpenId, analyzeMeal, analyzeMealByText, deleteMeal, deleteCloudFile, callCloudFunction,
}

