"""
Seed data management command to populate initial roles, sample users,
institution, and reference sources for demonstration and testing.
"""
from django.core.management.base import BaseCommand
from accounts.models import User, Institution, Course, Assignment
from documents.models import ReferenceSource
from analysis.models import ExclusionRule


class Command(BaseCommand):
    help = 'Populates the database with initial demonstration and test data'

    def handle(self, *args, **options):
        self.stdout.write("Seeding database...")

        # 1. Institution
        inst, _ = Institution.objects.get_or_create(
            name="Metropolitan Academic Institute",
            defaults={
                'short_name': 'MAI',
                'domain': 'metropolitan.edu',
                'is_active': True,
            }
        )
        self.stdout.write(f"Institution: {inst.name}")

        # 2. Users (Admin, Teacher, Student)
        admin_user, created = User.objects.get_or_create(
            username='admin',
            defaults={
                'email': 'admin@metropolitan.edu',
                'first_name': 'System',
                'last_name': 'Administrator',
                'role': User.Role.ADMIN,
                'institution': inst,
                'is_staff': True,
                'is_superuser': True,
                'is_verified': True,
            }
        )
        if created:
            admin_user.set_password('admin12345')
            admin_user.save()
            self.stdout.write("Created Admin: admin / admin12345")

        teacher_user, created = User.objects.get_or_create(
            username='dr_smith',
            defaults={
                'email': 'dr.smith@metropolitan.edu',
                'first_name': 'Eleanor',
                'last_name': 'Smith',
                'role': User.Role.TEACHER,
                'institution': inst,
                'department': 'Computer Science',
                'is_verified': True,
            }
        )
        if created:
            teacher_user.set_password('teacher123')
            teacher_user.save()
            self.stdout.write("Created Teacher: dr_smith / teacher123")

        student_user, created = User.objects.get_or_create(
            username='alice_student',
            defaults={
                'email': 'alice@student.metropolitan.edu',
                'first_name': 'Alice',
                'last_name': 'Johnson',
                'role': User.Role.STUDENT,
                'institution': inst,
                'department': 'Computer Science',
                'is_verified': True,
            }
        )
        if created:
            student_user.set_password('student123')
            student_user.save()
            self.stdout.write("Created Student: alice_student / student123")

        # 3. Course and Assignment
        course, _ = Course.objects.get_or_create(
            code="CS-401",
            institution=inst,
            defaults={
                'name': 'Advanced Software Engineering and Ethics',
                'instructor': teacher_user,
            }
        )
        course.students.add(student_user)

        assignment, _ = Assignment.objects.get_or_create(
            title="Term Research Paper: Modern Cloud Architectures",
            course=course,
            defaults={
                'created_by': teacher_user,
                'description': 'Original research synthesis on distributed and cloud microservices.',
                'max_similarity_threshold': 20,
                'allow_self_comparison': True,
            }
        )

        # 4. Default Exclusion Rules
        ExclusionRule.objects.get_or_create(
            name="Standard Bibliography & References Filter",
            rule_type=ExclusionRule.RuleType.BIBLIOGRAPHY,
            institution=inst,
            defaults={'is_enabled': True}
        )
        ExclusionRule.objects.get_or_create(
            name="Standard Direct Quotation Filter",
            rule_type=ExclusionRule.RuleType.QUOTATION,
            institution=inst,
            defaults={'is_enabled': True}
        )
        ExclusionRule.objects.get_or_create(
            name="Academic Parenthetical Citations",
            rule_type=ExclusionRule.RuleType.CITATION,
            institution=inst,
            defaults={'is_enabled': True}
        )
        ExclusionRule.objects.get_or_create(
            name="Minimum Word Count Threshold (5 words)",
            rule_type=ExclusionRule.RuleType.MIN_WORDS,
            institution=inst,
            defaults={'min_word_count': 5, 'is_enabled': True}
        )

        # 5. Reference Sources
        ref1, _ = ReferenceSource.objects.get_or_create(
            title="Principles of Distributed Systems and Cloud Scalability",
            defaults={
                'author': 'Prof. Arthur Pendelton',
                'source_type': ReferenceSource.SourceType.INSTITUTIONAL,
                'institution': inst,
                'retrieved_text': (
                    "Distributed computing systems are composed of autonomous computational entities "
                    "that communicate and coordinate their actions solely by message passing. "
                    "The primary benefits of distributed systems include horizontal scalability, "
                    "enhanced fault tolerance through redundancy, and lower latency through geographic distribution. "
                    "However, designing distributed algorithms requires addressing fundamental challenges "
                    "including consensus in asynchronous networks, network partitioning, and clock synchronization. "
                    "According to Brewer's CAP theorem, a distributed data store can simultaneously provide at most "
                    "two out of three guarantees: consistency, availability, and partition tolerance."
                ),
                'word_count': 82,
            }
        )

        ref2, _ = ReferenceSource.objects.get_or_create(
            title="Academic Research Integrity and Plagiarism in Higher Education",
            defaults={
                'author': 'Dr. Marcus Vance',
                'source_type': ReferenceSource.SourceType.ACADEMIC,
                'url': 'https://openacademic.org/papers/integrity-2024',
                'doi': '10.1000/182/academic.integrity.2024',
                'retrieved_text': (
                    "Plagiarism represents the uncredited appropriation of another author's thoughts, "
                    "ideas, language, or expressions. In educational settings, institutional integrity "
                    "mandates that all referenced concepts be appropriately documented with citations. "
                    "Automated similarity detection software provides an objective baseline by identifying "
                    "textual alignment against corpus indices, yet academic discretion is necessary to distinguish "
                    "between improper attribution and acceptable disciplinary jargon."
                ),
                'word_count': 64,
            }
        )

        self.stdout.write(self.style.SUCCESS("Successfully seeded demonstration data!"))
