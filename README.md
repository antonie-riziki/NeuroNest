# NeuroNest Intelligence Assistant (NIA)

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-6.0-green.svg)](https://www.djangoproject.com/)
[![LangChain](https://img.shields.io/badge/LangChain-Enabled-orange.svg)](https://www.langchain.com/)
[![Supabase](https://img.shields.io/badge/Supabase-Backend-emerald.svg)](https://supabase.com/)
[![Google Gemini](https://img.shields.io/badge/Google%20Gemini-Flash%20Lite-blueviolet.svg)](https://ai.google.dev/)

**NeuroNest Intelligence Assistant (NIA)** is an AI-driven, evidence-based neurodiversity support platform. It provides personalized, context-aware guidance and knowledge retrieval for caregivers, parents, educators, and clinicians supporting neurodivergent children.

By combining multi-tenant personalized Retrieval-Augmented Generation (RAG) with adaptive audience prompting, NIA delivers tailored advice while adhering strictly to clinical safety boundaries and ethical guidelines.

---

## 🚀 Key Features

* **Empathetic & Context-Aware AI Chatbot**:
  * Adapts messaging style dynamically based on audience context (Caregiver mode vs. Child companion mode).
  * Considers child demographics, specific neurodivergent concerns/diagnoses, and conversation history.
  * Mandatory safety footers, clinical referrals, and strict hallucination prevention rules.
* **Multi-Tenant Personalized RAG System**:
  * Dual-layer FAISS vector store indexing global clinical literature (e.g., DSM-5 guides) and child-specific documents.
  * Automatic staleness detection and incremental index re-building upon new document ingestion.
  * Supports dynamic file loading across multiple formats: `.pdf`, `.csv`, `.docx`, `.doc`.
* **Caregiver & Child Profile Management**:
  * Authentication powered by Supabase Auth (GoTrue).
  * Support for multiple child profiles per caregiver account with active profile switching.
  * Integrated profile avatar upload directly to Supabase Storage buckets.
* **Interactive Knowledge Base & Search**:
  * Full-text global knowledge retrieval endpoint.
  * Document upload portal for attaching personalized medical or educational records to individual child profiles.

---

## 🛠️ Architecture & Tech Stack

### Core Stack
* **Framework**: Django 6.0 (Web Framework & Session Management)
* **LLM & Embeddings**: Google Gemini (`gemini-3.1-flash-lite`, `gemini-embedding-2`) via `langchain-google-genai`
* **Vector Database**: FAISS (`faiss-cpu`) managed via LangChain
* **Authentication & Database**: Supabase GoTrue Auth & REST API
* **File Storage**: Supabase Storage (`child-profiles` bucket) & Django local file storage for knowledge docs

### System Architecture
```
                        +---------------------------------+
                        |   Caregiver / Frontend UI       |
                        +---------------------------------+
                                         |
                                         v
                        +---------------------------------+
                        |   Django Core & Engine Views    |
                        +---------------------------------+
                         /               |               \
                        /                v                \
  +-----------------------+  +-----------------------+  +-------------------------+
  |    Supabase Auth      |  |     LangChain RAG     |  |   Document Ingestion    |
  | & Profile Management  |  |   Pipeline & Prompt   |  |   & FAISS Vector Stores |
  +-----------------------+  +-----------------------+  +-------------------------+
                                         |                           |
                                         v                           v
                             +-----------------------+   +-----------------------+
                             | Google Gemini LLM API |   |  Global & Child-Specific|
                             | & Embeddings Model    |   |  Local Index Storage  |
                             +-----------------------+   +-----------------------+
```

---

## 📂 Repository Structure

```
.
├── LICENSE
├── README.md
└── NIA/                       # Django project root
    ├── manage.py
    ├── requirements.txt       # Project dependencies
    ├── NIA/                   # Core Django project settings & URLs
    │   ├── settings.py
    │   ├── urls.py
    │   ├── wsgi.py
    │   └── asgi.py
    ├── apps/                  # Application modules
    │   ├── core/              # Authentication & child profile management
    │   │   ├── models.py
    │   │   ├── views.py
    │   │   ├── supabase_client.py   # Supabase REST & Auth integration
    │   │   └── apps.py
    │   └── engine/            # AI RAG pipeline & vector search engine
    │       ├── ingestion.py   # Document loader (PDF, CSV, DOCX) & Gemini model init
    │       ├── pipeline.py    # FAISS caching, retriever build & QA chain
    │       ├── prompt_builder.py # Adaptive prompt templates & safety rules
    │       ├── vector_store.py# Utility vector store functions
    │       └── views.py      # Chatbot and Knowledgebase endpoints
    ├── templates/             # HTML UI templates
    │   ├── auth.html          # Login / Signup page
    │   ├── child_profile.html # Child profile creation & switcher
    │   ├── chatbot.html       # AI Chat interface
    │   └── knowledge_graph.html # Knowledge base & document uploader
    ├── static/                # Static assets & seed clinical literature
    │   └── docs/              # Default clinical documents (e.g., DSM-5)
    ├── media/                 # Ingested user & child document storage
    └── vector_store_db/       # Persisted FAISS index files (Global & Child-specific)
```

---

## 📋 Prerequisites

* **Python**: `3.10` or higher
* **Google Gemini API Key**: Obtainable from [Google AI Studio](https://aistudio.google.com/)
* **Supabase Project**: Active Supabase project with GoTrue Auth enabled and a `caregivers` / `children` REST table schema.

---

## ⚙️ Environment Configuration

Create a `.env` file in the root directory (parent of `NIA/`):

```env
# Google Gemini API Key
GOOGLE_API_KEY=your_google_gemini_api_key

# Supabase Configuration
SUPABASE_URL=https://your-supabase-project-id.supabase.co
SUPABASE_KEY=your_supabase_anon_public_key
```

---

## 💻 Installation & Setup

1. **Clone the Repository**:
   ```bash
   git clone https://github.com/your-org/NeuroNest.git
   cd NeuroNest
   ```

2. **Create and Activate a Virtual Environment**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install Dependencies**:
   ```bash
   pip install -r NIA/requirements.txt
   ```

4. **Prepare Environment File**:
   Create the `.env` file as shown in the [Environment Configuration](#-environment-configuration) section above.

5. **Run Database Migrations & Django Server**:
   ```bash
   cd NIA
   python manage.py migrate
   python manage.py runserver
   ```

6. **Access the Application**:
   Open your browser and navigate to `http://127.0.0.1:8000/`.

---

## 📖 Usage Guide

### 1. Authentication & Profile Creation
* Navigate to `/` to sign up or sign in using your caregiver account.
* Once logged in, add child profiles including name, date of birth, primary concern/diagnosis, language preferences, and optional avatar photo.

### 2. Interactive AI Chat
* Navigate to `/chat/`.
* Select an active child profile from the dropdown header to scope the context.
* Engage with NIA for personalized recommendations regarding sensory processing, emotional regulation, communication, daily routines, and caregiver wellbeing.

### 3. Knowledge Base & Custom Ingestion
* Navigate to `/knowledgebase/`.
* Use the search bar to query global clinical knowledge.
* Upload custom documents (`.pdf`, `.csv`, `.docx`) attached either globally or to a specific child's profile. The RAG pipeline will automatically index the file into the local FAISS database for immediate use in chat conversations.

---

## 🛡️ Safety, Ethics & Escalation

NIA is built with strict safety boundaries and guardrails programmed into the model prompts (`apps/engine/prompt_builder.py`):

* **No Diagnosis or Medication Advice**: NIA does not diagnose medical conditions, prescribe medication, or adjust therapeutic dosages.
* **Escalation Protocol**: In cases of self-harm, medical emergencies, abuse, or imminent danger, NIA advises immediate professional and emergency contact.
* **Disclaimers**: Every AI-generated response includes a mandatory footer:
  > *"NIA provides educational information and support. Always discuss medical, therapeutic, or diagnostic concerns with your child's clinician."*

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
