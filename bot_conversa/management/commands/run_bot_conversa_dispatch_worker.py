import time

from django.core.management.base import BaseCommand

from bot_conversa.services import BotConversaDispatchWorkerService


class Command(BaseCommand):
    help = 'Processa disparos pendentes/em andamento do Bot Conversa sem depender da tela aberta.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--loop',
            action='store_true',
            help='Mantem o worker em execucao continua.',
        )
        parser.add_argument(
            '--sleep-seconds',
            type=int,
            default=5,
            help='Intervalo entre ciclos no modo --loop.',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=20,
            help='Numero maximo de dispatches avaliados por ciclo.',
        )

    def handle(self, *args, **options):
        loop = options['loop']
        sleep_seconds = max(1, options['sleep_seconds'])
        limit = max(1, options['limit'])

        while True:
            processed_count = BotConversaDispatchWorkerService.run_cycle(limit=limit)
            self.stdout.write(
                self.style.SUCCESS(
                    f'Worker do Bot Conversa executado. Dispatches avaliados: {processed_count}'
                )
            )

            if not loop:
                break

            time.sleep(sleep_seconds)
