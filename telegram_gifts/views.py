from django.shortcuts import render
import asyncio
from collections_parser import fetch_collections
from gifts_parser import fetch_nfts_for_sale

async def index(request):
    collections = await fetch_collections()
    selected_collection_id = request.GET.get('collection_id')
    nfts = []
    if selected_collection_id:
        nfts = await fetch_nfts_for_sale(selected_collection_id)
    
    context = {
        'collections': collections,
        'nfts': nfts,
        'selected_collection_id': selected_collection_id,
    }
    return render(request, 'index.html', context)