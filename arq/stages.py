"""Standard project stages and client-facing explanations."""

from .config import slugify

STANDARD_STAGES = (
    'Proposta', 'Briefing e Levantamento', 'Estudos Preliminares / Anteprojeto',
    'Projeto 3D', 'Projeto Executivo', 'Entrega Final', 'Serviços extras',
)

EXPLANATIONS = {
    'pt': (
        ('Apresentação do escopo, das condições e do planejamento do projeto.',
         'Proposta de serviços com etapas, prazos e valores previstos.'),
        ('Entendimento das necessidades, preferências e características do espaço.',
         'Briefing e registros do levantamento, como medidas, fotos e informações do imóvel.'),
        ('Desenvolvimento das primeiras soluções e definição da proposta de organização dos ambientes.',
         'Estudos de layout, plantas e referências para avaliação e ajustes.'),
        ('Visualização da proposta para entender volumes, materiais e a atmosfera dos ambientes.',
         'Imagens e vistas 3D dos ambientes previstos no escopo.'),
        ('Detalhamento das soluções aprovadas para orientar a execução.',
         'Desenhos técnicos, detalhamentos e especificações previstos no escopo.'),
        ('Organização e disponibilização dos documentos finais do projeto.',
         'Conjunto final de arquivos e orientações de uso dos documentos.'),
        ('Atividades complementares acordadas além do escopo inicial.',
         'Materiais e registros dos serviços adicionais contratados.'),
    ),
    'en': (
        ('Presentation of the scope, terms and project plan.', 'Service proposal with planned stages, dates and fees.'),
        ('Understanding needs, preferences and the existing space.', 'Brief and survey records, such as measurements, photos and property information.'),
        ('Exploring initial solutions and defining the arrangement of spaces.', 'Layout studies, plans and references for review and refinement.'),
        ('Visualizing volumes, materials and the atmosphere of the design.', '3D images and views of spaces included in the scope.'),
        ('Detailing approved solutions to guide implementation.', 'Technical drawings, details and specifications included in the scope.'),
        ('Organizing and sharing the final project documents.', 'Final files and guidance on using the documents.'),
        ('Additional activities agreed beyond the initial scope.', 'Materials and records for the additional services commissioned.'),
    ),
}


def stage_explanation(number, label, language):
    if number is None or not 1 <= number <= len(STANDARD_STAGES):
        return None
    if slugify(label) != slugify(STANDARD_STAGES[number - 1]):
        return None
    return EXPLANATIONS.get(language, EXPLANATIONS['pt'])[number - 1]
