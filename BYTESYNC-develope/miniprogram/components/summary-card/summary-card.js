// components/summary-card/summary-card.js
const { calcPct } = require('../../utils/nutrition')

Component({
  properties: {
    userName:    { type: String, value: '— —'  },
    role:        { type: String, value: ''     },  // 'me' | 'ta'
    calories:    { type: Number, value: 0      },
    calorieGoal: { type: Number, value: 2000   },
    protein:     { type: Number, value: 0      },
    carbs:       { type: Number, value: 0      },
    fat:         { type: Number, value: 0      },
    proteinGoal: { type: Number, value: 60     },
    carbsGoal:   { type: Number, value: 250    },
    fatGoal:     { type: Number, value: 65     }
  },

  data: {
    caloriePct: 0
  },

  observers: {
    'calories, calorieGoal'() {
      const { calories, calorieGoal } = this.data
      this.setData({ caloriePct: calcPct(calories, calorieGoal) })
    }
  },

  methods: {}
})
