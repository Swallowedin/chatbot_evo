import streamlit as st
from openai import OpenAI
import json
from typing import Dict, List, Tuple, Optional
import re
from prestations import get_prestations, get_facteur_urgence

# Configuration de la page
st.set_page_config(
    page_title="Assistant Juridique - Identification de Prestations",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Configuration OpenAI
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# Style CSS personnalisé
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(90deg, #1e3a8a 0%, #3b82f6 100%);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        text-align: center;
        margin-bottom: 2rem;
    }
    
    .chat-message {
        padding: 1rem;
        border-radius: 10px;
        margin: 1rem 0;
        border-left: 4px solid #3b82f6;
    }
    
    .user-message {
        background-color: #f0f9ff;
        border-left-color: #0ea5e9;
    }
    
    .assistant-message {
        background-color: #f8fafc;
        border-left-color: #1e40af;
    }
    
    .prestation-card {
        background: white;
        padding: 1rem;
        border-radius: 8px;
        border: 1px solid #e2e8f0;
        margin: 0.5rem 0;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
    
    .price-tag {
        background: #10b981;
        color: white;
        padding: 0.25rem 0.75rem;
        border-radius: 20px;
        font-weight: bold;
        display: inline-block;
        margin: 0.5rem 0;
    }
    
    .urgent-price {
        background: #f59e0b;
    }
    
    .sidebar-info {
        background-color: #f1f5f9;
        padding: 1rem;
        border-radius: 8px;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)

class AssistantJuridique:
    def __init__(self):
        self.prestations = get_prestations()
        self.facteur_urgence = get_facteur_urgence()
        
    def extraire_mots_cles(self, texte: str) -> List[str]:
        """Extrait les mots-clés pertinents du texte de l'utilisateur"""
        mots_cles_juridiques = [
            'contrat', 'bail', 'commercial', 'travail', 'licenciement', 'création', 'société',
            'immobilier', 'divorce', 'succession', 'pénal', 'défense', 'contentieux',
            'marque', 'brevet', 'propriété intellectuelle', 'RGPD', 'données',
            'construction', 'liquidation', 'redressement', 'sauvegarde',
            'association', 'fondation', 'compliance', 'fusion', 'acquisition'
        ]
        
        texte_lower = texte.lower()
        mots_trouves = [mot for mot in mots_cles_juridiques if mot in texte_lower]
        return mots_trouves
    
    def rechercher_prestations_pertinentes(self, query: str, mots_cles: List[str]) -> List[Dict]:
        """Recherche les prestations pertinentes selon la requête"""
        resultats = []
        query_lower = query.lower()
        
        for domaine_id, domaine_data in self.prestations.items():
            for prestation_id, prestation_data in domaine_data["prestations"].items():
                score = 0
                
                # Recherche dans le label
                if any(mot in prestation_data["label"].lower() for mot in mots_cles):
                    score += 3
                
                # Recherche dans la définition
                if any(mot in prestation_data["definition"].lower() for mot in mots_cles):
                    score += 2
                
                # Recherche directe dans la query
                for mot in query_lower.split():
                    if len(mot) > 3:
                        if mot in prestation_data["label"].lower():
                            score += 4
                        if mot in prestation_data["definition"].lower():
                            score += 2
                        if mot in domaine_data["label"].lower():
                            score += 1
                
                if score > 0:
                    resultats.append({
                        'domaine': domaine_data["label"],
                        'domaine_id': domaine_id,
                        'prestation_id': prestation_id,
                        'prestation': prestation_data,
                        'score': score
                    })
        
        # Trier par score décroissant
        resultats.sort(key=lambda x: x['score'], reverse=True)
        return resultats[:5]  # Top 5
    
    def generer_questions_clarification(self, resultats: List[Dict], query: str) -> str:
        """Génère des questions de clarification basées sur les résultats"""
        if not resultats:
            return "Je n'ai pas trouvé de prestations correspondant exactement à votre demande. Pouvez-vous me donner plus de détails sur votre situation juridique ?"
        
        domaines_uniques = list(set([r['domaine'] for r in resultats]))
        
        if len(domaines_uniques) > 2:
            questions = [
                "Pour mieux vous orienter, pouvez-vous me préciser :",
                f"- Votre situation concerne-t-elle plutôt : {', '.join(domaines_uniques[:3])} ?",
                "- S'agit-il d'une situation urgente ?",
                "- Êtes-vous un particulier ou une entreprise ?"
            ]
        else:
            questions = [
                "J'ai identifié quelques prestations qui pourraient vous convenir. Pour affiner :",
                "- Pouvez-vous me donner plus de détails sur votre situation ?",
                "- Y a-t-il une urgence particulière ?",
                "- Avez-vous déjà entamé des démarches juridiques ?"
            ]
        
        return "\n".join(questions)
    
    def analyser_avec_gpt(self, query: str, historique: List[Dict]) -> Dict:
        """Utilise GPT-4o-mini pour analyser la demande et suggérer des prestations"""
        
        # Préparer le contexte des prestations pour GPT
        prestations_context = ""
        for domaine_id, domaine_data in self.prestations.items():
            prestations_context += f"\n{domaine_data['label']}:\n"
            for prestation_id, prestation_data in domaine_data["prestations"].items():
                prestations_context += f"  - {prestation_data['label']} ({prestation_data['tarif']}€): {prestation_data['definition']}\n"
        
        # Construire l'historique de conversation
        conversation_history = ""
        for msg in historique[-5:]:  # Garder les 5 derniers messages
            conversation_history += f"{msg['role']}: {msg['content']}\n"
        
        prompt = f"""Tu es un assistant juridique expert. Ton rôle est d'identifier la ou les prestations juridiques les plus appropriées selon la demande du client.

PRESTATIONS DISPONIBLES:
{prestations_context}

HISTORIQUE DE CONVERSATION:
{conversation_history}

NOUVELLE DEMANDE: {query}

Analyse cette demande et réponds au format JSON suivant:
{{
    "prestations_recommandees": [
        {{
            "domaine_id": "id_du_domaine",
            "prestation_id": "id_de_la_prestation", 
            "score_pertinence": 1-10,
            "justification": "pourquoi cette prestation correspond"
        }}
    ],
    "questions_clarification": [
        "question 1 pour affiner le besoin",
        "question 2 si nécessaire"
    ],
    "analyse_situation": "résumé de la situation du client",
    "urgence_detectee": true/false,
    "type_client": "particulier/entreprise/indetermine"
}}

Sois précis et ne recommande que les prestations vraiment pertinentes."""

        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=1500
            )
            
            result_text = response.choices[0].message.content
            
            # Nettoyer et parser le JSON
            result_text = result_text.strip()
            if result_text.startswith("```json"):
                result_text = result_text[7:-3]
            elif result_text.startswith("```"):
                result_text = result_text[3:-3]
            
            result = json.loads(result_text)
            return result
            
        except Exception as e:
            st.error(f"Erreur lors de l'analyse GPT: {str(e)}")
            return {
                "prestations_recommandees": [],
                "questions_clarification": ["Pouvez-vous reformuler votre demande ?"],
                "analyse_situation": "Erreur d'analyse",
                "urgence_detectee": False,
                "type_client": "indetermine"
            }

def afficher_prestation_card(prestation_info: Dict, urgent: bool = False):
    """Affiche une carte de prestation"""
    prestation = prestation_info['prestation']
    tarif = prestation['tarif']
    
    if urgent:
        tarif_urgent = int(tarif * get_facteur_urgence())
        price_class = "price-tag urgent-price"
        tarif_text = f"{tarif_urgent}€ (urgent) - Normal: {tarif}€"
    else:
        price_class = "price-tag"
        tarif_text = f"{tarif}€"
    
    st.markdown(f"""
    <div class="prestation-card">
        <h4>{prestation['label']}</h4>
        <div class="{price_class}">{tarif_text}</div>
        <p><strong>Domaine:</strong> {prestation_info['domaine']}</p>
        <p><strong>Description:</strong> {prestation['definition']}</p>
    </div>
    """, unsafe_allow_html=True)

def main():
    # En-tête
    st.markdown("""
    <div class="main-header">
        <h1>⚖️ Assistant Juridique Intelligent</h1>
        <p>Identifiez rapidement la prestation juridique adaptée à votre situation</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Initialisation de l'assistant
    if 'assistant' not in st.session_state:
        st.session_state.assistant = AssistantJuridique()
    
    # Initialisation de l'historique de conversation
    if 'messages' not in st.session_state:
        st.session_state.messages = []
    
    # Sidebar avec informations
    with st.sidebar:
        st.markdown("### 📋 Informations")
        st.markdown("""
        <div class="sidebar-info">
        <h4>Comment utiliser cet assistant :</h4>
        <ul>
            <li>Décrivez votre situation juridique</li>
            <li>Répondez aux questions de clarification</li>
            <li>Obtenez les prestations adaptées avec leurs tarifs</li>
        </ul>
        
        <h4>Exemples de demandes :</h4>
        <ul>
            <li>"J'ai besoin d'un bail commercial"</li>
            <li>"Je veux créer une société"</li>
            <li>"Problème avec mon locataire"</li>
            <li>"Divorce à l'amiable"</li>
        </ul>
        </div>
        """, unsafe_allow_html=True)
        
        if st.button("🗑️ Nouvelle conversation"):
            st.session_state.messages = []
            st.rerun()
    
    # Zone de chat principal
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown("### 💬 Conversation")
        
        # Affichage de l'historique
        for message in st.session_state.messages:
            css_class = "user-message" if message["role"] == "user" else "assistant-message"
            with st.container():
                st.markdown(f"""
                <div class="chat-message {css_class}">
                    <strong>{'👤 Vous' if message["role"] == "user" else '🤖 Assistant'}:</strong><br>
                    {message["content"]}
                </div>
                """, unsafe_allow_html=True)
        
        # Input utilisateur
        user_input = st.chat_input("Décrivez votre situation juridique...")
        
        if user_input:
            # Ajouter le message utilisateur
            st.session_state.messages.append({"role": "user", "content": user_input})
            
            # Analyser avec GPT
            with st.spinner("Analyse en cours..."):
                analyse = st.session_state.assistant.analyser_avec_gpt(
                    user_input, 
                    st.session_state.messages
                )
            
            # Préparer la réponse
            response_parts = []
            
            if analyse["analyse_situation"]:
                response_parts.append(f"**Analyse de votre situation :** {analyse['analyse_situation']}")
            
            # Ajouter les prestations recommandées à la colonne de droite
            if analyse["prestations_recommandees"]:
                st.session_state.prestations_actuelles = analyse["prestations_recommandees"]
                st.session_state.urgence_detectee = analyse.get("urgence_detectee", False)
            
            # Questions de clarification
            if analyse["questions_clarification"]:
                response_parts.append("**Questions pour mieux vous aider :**")
                for i, question in enumerate(analyse["questions_clarification"], 1):
                    response_parts.append(f"{i}. {question}")
            
            # Joindre la réponse
            assistant_response = "\n\n".join(response_parts)
            st.session_state.messages.append({"role": "assistant", "content": assistant_response})
            
            st.rerun()
    
    with col2:
        st.markdown("### 📄 Prestations Recommandées")
        
        if hasattr(st.session_state, 'prestations_actuelles') and st.session_state.prestations_actuelles:
            urgence = getattr(st.session_state, 'urgence_detectee', False)
            
            if urgence:
                st.warning("⚠️ Urgence détectée - Tarifs majorés de 50%")
            
            for prestation_rec in st.session_state.prestations_actuelles:
                # Récupérer les données complètes de la prestation
                prestations = get_prestations()
                domaine_id = prestation_rec["domaine_id"]
                prestation_id = prestation_rec["prestation_id"]
                
                if domaine_id in prestations and prestation_id in prestations[domaine_id]["prestations"]:
                    prestation_info = {
                        'domaine': prestations[domaine_id]["label"],
                        'prestation': prestations[domaine_id]["prestations"][prestation_id],
                        'score': prestation_rec.get("score_pertinence", 0)
                    }
                    
                    afficher_prestation_card(prestation_info, urgence)
                    
                    with st.expander(f"💡 Pourquoi cette prestation ? (Score: {prestation_rec.get('score_pertinence', 0)}/10)"):
                        st.write(prestation_rec.get("justification", "Correspond à votre demande"))
        else:
            st.info("Les prestations recommandées apparaîtront ici après votre première question.")
            
            # Afficher quelques prestations populaires
            st.markdown("**Prestations populaires :**")
            prestations = get_prestations()
            prestations_populaires = [
                ("droit_civil_contrats", "consultation_initiale"),
                ("droit_des_affaires", "creation_entreprise"),
                ("droit_immobilier_commercial", "redaction_bail_commercial"),
                ("droit_de_la_famille", "procedure_divorce_amiable")
            ]
            
            for domaine_id, prestation_id in prestations_populaires:
                if domaine_id in prestations and prestation_id in prestations[domaine_id]["prestations"]:
                    prestation_info = {
                        'domaine': prestations[domaine_id]["label"],
                        'prestation': prestations[domaine_id]["prestations"][prestation_id]
                    }
                    with st.expander(f"{prestation_info['prestation']['label']} - {prestation_info['prestation']['tarif']}€"):
                        st.write(prestation_info['prestation']['definition'])

if __name__ == "__main__":
    main()
