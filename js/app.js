// Stelle sicher, dass Vue.js von einem CDN geladen wird
const vueScript = document.createElement('script');
vueScript.src = 'https://unpkg.com/vue@3.2.37/dist/vue.global.prod.js';
document.head.appendChild(vueScript);

vueScript.onload = () => {
  const { createApp } = Vue;

  createApp({
    data() {
      return {
        name: "Chaima",
        skills: [
          "kochen", 
          ["immer", "wenn es lustig ist", "ohne grund"], 
          { 
            name: "lachen",
            details: ["immer", "wenn es lustig ist", "ohne grund"]
          }, 
          "sachen machen"
        ],
        message: "I miss my wife"
      };
    },
    methods: {
      // Methode, um den ersten Detail-Eintrag eines Skills zu bekommen
      getFirstSkillDetail(skillName) {
        const skill = this.skills.find(item => 
          typeof item === 'object' && item.name === skillName
        );
        return skill && skill.details.length > 0 ? skill.details[0] : 'Nicht gefunden';
      },
      
      changeMessage() {
        this.message = "Nachricht geändert! Willkommen, " + this.name + "!";
      }
    }
  }).mount('#app');
}
