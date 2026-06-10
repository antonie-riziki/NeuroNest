from django.shortcuts import render

# Create your views here.
def knowledgebase(request):
    return render(request, 'knowledge_graph.html')

    
def chat(request):
    return render(request, 'chatbot.html')
    