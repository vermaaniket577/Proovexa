# Generated for dynamic AI API Settings configuration

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('analysis', '0005_aireport_ai_generated_only_cyan_pct_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='AIAPISettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('is_enabled', models.BooleanField(default=True, help_text='Master switch to enable or disable external AI API calls.')),
                ('provider', models.CharField(choices=[('auto', 'Auto (Gemini -> OpenAI -> Local Fallback)'), ('gemini', 'Google Gemini API Only'), ('openai', 'OpenAI API Only'), ('local', 'Calibrated Local AI Engine Only (Offline)')], default='auto', help_text='Active external AI provider preference.', max_length=20)),
                ('gemini_api_key', models.CharField(blank=True, default='', help_text='Google Gemini API Key (e.g. AIzaSy...)', max_length=255)),
                ('gemini_model', models.CharField(default='gemini-1.5-flash', help_text='Gemini model name (e.g. gemini-1.5-flash, gemini-2.0-flash, gemini-1.5-pro)', max_length=64)),
                ('openai_api_key', models.CharField(blank=True, default='', help_text='OpenAI API Key (e.g. sk-proj-...)', max_length=255)),
                ('openai_model', models.CharField(default='gpt-4o-mini', help_text='OpenAI model identifier (e.g. gpt-4o-mini, gpt-4o, o3-mini)', max_length=64)),
                ('timeout_seconds', models.PositiveIntegerField(default=15, help_text='Timeout in seconds for API HTTP requests (5 - 60).')),
                ('temperature', models.FloatField(default=0.1, help_text='Sampling temperature for deterministic classification (0.0 - 1.0).')),
                ('max_tokens', models.PositiveIntegerField(default=2048, help_text='Maximum output tokens requested from LLM APIs.')),
                ('enable_ai_writing_detection', models.BooleanField(default=True, help_text='Enable live AI writing analysis cross-validation via external API.')),
                ('enable_paraphrase_detection', models.BooleanField(default=True, help_text='Enable semantic paraphrase cross-examination during similarity checks.')),
                ('blend_weight', models.FloatField(default=0.5, help_text='Blend weight for external AI score vs calibrated local sliding window (0.0 to 1.0, default 0.5).')),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='ai_settings_updates', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'AI API Settings',
                'verbose_name_plural': 'AI API Settings',
            },
        ),
    ]
