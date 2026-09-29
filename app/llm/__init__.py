"""
app/llm

Layer AI provider RIN.

Package ini SENGAJA tidak meng-import apa pun di level module, untuk
menghindari circular import (providers mengimpor app.llm.base).
Gunakan import eksplisit:

    from app.llm.router import AIProviderRouter, PROVIDER_IDS
    from app.llm.base import AIProvider, ChatMessage
"""
