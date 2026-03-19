import time

from django.core.management.base import BaseCommand

from imports.services import ImportJobWorkerService


class Command(BaseCommand):
    help = 'Processa jobs pendentes de importacao XLSX em background.'

    def add_arguments(self, parser):
        parser.add_argument('--loop', action='store_true', help='Mantem o worker em execucao continua.')
        parser.add_argument('--sleep-seconds', type=int, default=5, help='Intervalo entre ciclos no modo loop.')
        parser.add_argument('--limit', type=int, default=20, help='Numero maximo de jobs por ciclo.')
        parser.add_argument('--batch-size', type=int, default=20, help='Numero maximo de linhas por job em cada ciclo.')

    def handle(self, *args, **options):
        loop = options['loop']
        sleep_seconds = max(1, options['sleep_seconds'])
        limit = max(1, options['limit'])
        batch_size = max(1, options['batch_size'])

        while True:
            processed_count = ImportJobWorkerService.run_cycle(limit=limit, batch_size=batch_size)
            self.stdout.write(self.style.SUCCESS(f'Worker de importacao executado. Jobs avaliados: {processed_count}'))
            if not loop:
                break
            time.sleep(sleep_seconds)
