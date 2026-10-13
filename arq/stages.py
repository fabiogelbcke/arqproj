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
        ('',
         'Briefing\nConceito\nPesquisa\nMoodboard\nLevantamento técnico'),
        ('', 'Plantas humanizadas\nMoodboard\nImagens de referência'),
        ('', 'Imagens realistas'),
        ('', 'Plantas executivas\nDetalhamento de marcenaria\nForros e paginações\nEspecificações de materiais\nMemorial descritivo'),
        ('', 'Projeto completo de esquadrias, marcenaria, iluminação, mobiliário, climatização, entre outros.'),
        ('Atividades complementares acordadas além do escopo inicial.',
         'Materiais e registros dos serviços adicionais contratados.'),
    ),
    'en': (
        ('Presentation of the scope, terms and project plan.', 'Service proposal with planned stages, dates and fees.'),
        ('', 'Brief\nConcept\nResearch\nMoodboard\nTechnical survey'),
        ('', 'Illustrated floor plans\nMoodboard\nReference images'),
        ('', 'Realistic images'),
        ('', 'Construction drawings\nJoinery details\nCeiling and surface layouts\nMaterial specifications\nDescriptive report'),
        ('', 'Complete design for windows and doors, joinery, lighting, furniture, climate control, and more.'),
        ('Additional activities agreed beyond the initial scope.', 'Materials and records for the additional services commissioned.'),
    ),
}

PRELIMINARY_ACTIVITIES = {
    'pt': ('Estudo de layout', 'Distribuição dos ambientes', 'Estudos de mobiliário',
           'Definição dos fluxos', 'Primeiras definições de materiais'),
    'en': ('Layout study', 'Arrangement of spaces', 'Furniture studies',
           'Circulation planning', 'Initial material selections'),
}

MODELING_ACTIVITIES = {
    'pt': ('Modelagem tridimensional', 'Volumetrias', 'Aplicação de materiais'),
    'en': ('3D modeling', 'Volume studies', 'Material application'),
}


def stage_explanation(number, label, language):
    if number is None or not 1 <= number <= len(STANDARD_STAGES):
        return None
    if slugify(label) != slugify(STANDARD_STAGES[number - 1]):
        return None
    return EXPLANATIONS.get(language, EXPLANATIONS['pt'])[number - 1]
