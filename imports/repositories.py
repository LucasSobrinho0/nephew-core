from imports.models import ImportJob, ImportJobItem


class ImportJobRepository:
    @staticmethod
    def create(**kwargs):
        return ImportJob.objects.create(**kwargs)

    @staticmethod
    def get_for_organization_and_public_id(organization, public_id):
        return (
            ImportJob.objects.for_organization(organization)
            .with_related_objects()
            .filter(public_id=public_id)
            .first()
        )

    @staticmethod
    def list_recent_for_organization(organization, *, limit=5):
        return ImportJob.objects.for_organization(organization).with_related_objects()[:limit]

    @staticmethod
    def list_runnable_jobs(*, limit=20):
        return (
            ImportJob.objects.with_related_objects()
            .filter(status__in=[ImportJob.Status.PENDING, ImportJob.Status.RUNNING])
            .order_by('created_at')[:limit]
        )


class ImportJobItemRepository:
    @staticmethod
    def bulk_create(items, **kwargs):
        return ImportJobItem.objects.bulk_create(items, **kwargs)

    @staticmethod
    def list_for_job(job):
        return ImportJobItem.objects.for_job(job).with_related_objects().order_by('row_number')

    @staticmethod
    def list_pending_for_job(job, *, limit):
        return ImportJobItem.objects.pending().for_job(job).with_related_objects().order_by('row_number')[:limit]
