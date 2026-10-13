
from django.shortcuts import render


def home(request):
    context = {
        'platform_name': 'IELTS Mock Test Platform',
        'modules': [
            {
                'name': 'Reading',
                'description': 'Practice reading comprehension with timed questions.',
                'icon': '📖',
            },
            {
                'name': 'Listening',
                'description': 'Practice listening with exam-style audio sessions.',
                'icon': '🎧',
            },
            {
                'name': 'Writing',
                'description': 'Practice IELTS Writing Task 1 and Task 2.',
                'icon': '✍️',
            },
        ],
    }

    return render(request, 'home.html', context)
