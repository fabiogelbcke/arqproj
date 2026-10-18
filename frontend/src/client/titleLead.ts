// How a project's title splits into its lead ("/casa de praia", upright) and the
// rest (bold): the longest property or work type the name starts with, else its
// first word (Fabio, 18 Oct 2026). Matching ignores case and accents, and stops at
// whole words, so "Casarão Silva" isn't "Casa" + "rão silva".

const TYPES = [
  // Housing (Fabio's list)
  "Residência", "Casa", "Casa de praia", "Casa de campo", "Casa de serra", "Casa de veraneio", "Casa de vila",
  "Casa geminada", "Sobrado", "Apartamento", "Apartamento duplex", "Apartamento triplex", "Cobertura", "Loft",
  "Studio", "Kitnet", "Bangalô", "Chalé", "Cabana", "Sítio", "Chácara", "Fazenda", "Residencial",
  "Edifício residencial", "Condomínio residencial", "Conjunto habitacional", "Habitação de interesse social",
  "Moradia estudantil", "Coliving", "Residência sênior",
  // Housing: other ways people write them
  "Casa praia", "Casa na praia", "Casa da praia", "Casa pé na areia", "Casa campo", "Casa no campo", "Casa serra",
  "Casa na serra", "Casa de montanha", "Casa na montanha", "Casa de lago", "Casa no lago", "Casa de fazenda",
  "Casa de sítio", "Casa de chácara", "Casa térrea", "Casa assobradada", "Casa em condomínio", "Casa de condomínio",
  "Casa de hóspedes", "Casa de férias", "Casa de fim de semana", "Casa container", "Casa modular",
  "Casa pré-fabricada", "Casa de madeira", "Casa de vidro", "Casa na árvore", "Casarão", "Casinha", "Apto", "Apto.",
  "Ap.", "Apê", "Apartamento garden", "Apartamento giardino", "Apartamento térreo", "Apartamento de praia",
  "Apartamento na praia", "Apartamento compacto", "Garden", "Flat", "Penthouse", "Duplex", "Triplex",
  "Cobertura duplex", "Cobertura triplex", "Residência de praia", "Residência de campo", "Residência unifamiliar",
  "Residência multifamiliar",
  // Commerce and services
  "Loja", "Boutique", "Showroom", "Quiosque", "Pop-up store", "Shopping center", "Centro comercial",
  "Galeria comercial", "Edifício comercial", "Sala comercial", "Supermercado", "Minimercado", "Mercearia",
  "Hortifrúti", "Feira", "Mercado", "Farmácia", "Drogaria", "Livraria", "Papelaria", "Floricultura", "Pet shop",
  "Salão de beleza", "Barbearia", "Esmalteria", "Estúdio de tatuagem", "Lavanderia", "Assistência técnica",
  "Oficina", "Concessionária", "Locadora", "Agência bancária", "Agência de atendimento", "Posto de combustível",
  "Estacionamento", "Loja de rua", "Loja de shopping", "Ponto comercial", "Conjunto comercial",
  // Offices and work
  "Escritório", "Escritório de arquitetura", "Escritório de advocacia", "Escritório de contabilidade",
  "Escritório de engenharia", "Consultoria", "Agência", "Imobiliária", "Coworking", "Sede empresarial",
  "Sede administrativa", "Centro empresarial", "Edifício corporativo", "Campus corporativo", "Ateliê", "Estúdio",
  "Estúdio de fotografia", "Estúdio de gravação", "Estúdio audiovisual", "Laboratório de inovação",
  "Laje corporativa", "Andar corporativo", "Escritório corporativo", "Home studio",
  // Food
  "Restaurante", "Bistrô", "Café", "Cafeteria", "Padaria", "Confeitaria", "Doceria", "Chocolateria", "Sorveteria",
  "Gelateria", "Lanchonete", "Hamburgueria", "Pizzaria", "Churrascaria", "Cantina", "Bar", "Pub", "Cervejaria",
  "Adega", "Casa de chá", "Casa de sucos", "Praça de alimentação", "Cozinha industrial", "Cozinha compartilhada",
  "Cozinha de delivery", "Refeitório", "Buffet",
  // Health
  "Hospital", "Hospital-dia", "Maternidade", "Pronto atendimento", "Unidade de saúde", "Posto de saúde", "Clínica",
  "Clínica médica", "Clínica odontológica", "Clínica de psicologia", "Clínica de fisioterapia",
  "Clínica de estética", "Clínica de reabilitação", "Clínica veterinária", "Hospital veterinário", "Consultório",
  "Consultório médico", "Consultório odontológico", "Consultório de psicologia", "Consultório de nutrição",
  "Centro de diagnóstico", "Centro de imagem", "Laboratório", "Laboratório de análises clínicas", "Centro cirúrgico",
  "Centro de hemodiálise", "Banco de sangue", "Centro de vacinação", "Centro de reabilitação", "Centro terapêutico",
  "Spa", "Espaço de bem-estar", "Instituição de longa permanência",
  // Hospitality
  "Hotel", "Hotel boutique", "Apart-hotel", "Pousada", "Hostel", "Albergue", "Resort", "Eco resort", "Hospedaria",
  "Estalagem", "Motel", "Complexo turístico", "Vila de hospedagem", "Camping", "Glamping", "Refúgio",
  "Centro de visitantes",
  // Education and culture
  "Creche", "Escola", "Escola infantil", "Escola de ensino fundamental", "Escola de ensino médio", "Escola integral",
  "Escola técnica", "Escola profissionalizante", "Escola de idiomas", "Escola de música", "Escola de dança",
  "Escola de artes", "Faculdade", "Universidade", "Campus universitário", "Centro educacional",
  "Centro de treinamento", "Centro de pesquisa", "Instituto de pesquisa", "Laboratório de pesquisa", "Biblioteca",
  "Brinquedoteca", "Centro cultural", "Casa de cultura", "Museu", "Galeria de arte", "Teatro", "Anfiteatro",
  "Cinema", "Auditório", "Sala de concertos", "Casa de espetáculos", "Casa de shows", "Casa noturna",
  "Espaço de eventos", "Salão de festas", "Centro de convenções", "Pavilhão de exposições", "Parque de exposições",
  "Memorial", "Planetário", "Observatório", "Centro de entretenimento",
  // Sport and leisure
  "Academia", "Estúdio de pilates", "Estúdio de yoga", "Centro de treinamento esportivo", "Centro esportivo",
  "Complexo esportivo", "Clube", "Clube de campo", "Clube náutico", "Ginásio", "Estádio", "Arena",
  "Quadra esportiva", "Centro aquático", "Piscina", "Parque aquático", "Campo de futebol", "Campo de golfe",
  "Pista de atletismo", "Pista de skate", "Centro equestre", "Marina", "Área de lazer", "Espaço gourmet",
  "Churrasqueira", "Salão de jogos", "Playground",
  // Industry and logistics
  "Indústria", "Fábrica", "Unidade industrial", "Complexo industrial", "Parque industrial", "Galpão",
  "Galpão industrial", "Galpão logístico", "Armazém", "Depósito", "Centro de distribuição", "Centro logístico",
  "Terminal de cargas", "Entreposto", "Frigorífico", "Unidade de beneficiamento", "Oficina industrial",
  "Data center", "Central de manutenção", "Central de produção", "Usina",
  // Rural
  "Sede de fazenda", "Agroindústria", "Celeiro", "Estábulo", "Cavalariça", "Haras", "Curral", "Aviário", "Granja",
  "Viveiro", "Estufa", "Silo", "Armazém agrícola", "Unidade de armazenamento", "Laticínio", "Vinícola",
  "Adega de produção", "Cooperativa agrícola", "Centro de pesquisa agropecuária",
  // Public and community
  "Prefeitura", "Câmara municipal", "Fórum", "Tribunal", "Secretaria", "Centro administrativo",
  "Repartição pública", "Delegacia", "Quartel", "Base operacional", "Posto de atendimento", "Centro comunitário",
  "Centro de convivência", "Centro de assistência social", "Associação", "Sede de associação", "Sindicato",
  "Fundação", "Organização social", "Abrigo", "Casa de acolhimento", "Centro de acolhimento",
  "Unidade socioeducativa", "Unidade prisional", "Embaixada", "Consulado",
  // Religious and funerary
  "Igreja", "Capela", "Catedral", "Basílica", "Santuário", "Templo", "Sinagoga", "Mesquita", "Centro espírita",
  "Terreiro", "Mosteiro", "Convento", "Seminário", "Casa paroquial", "Centro pastoral", "Casa de retiro",
  "Cemitério", "Crematório", "Memorial funerário", "Capela mortuária", "Velório", "Funerária",
  // Transport and infrastructure
  "Aeroporto", "Terminal aeroportuário", "Rodoviária", "Terminal de passageiros", "Terminal urbano",
  "Estação ferroviária", "Estação de metrô", "Estação de transporte", "Terminal hidroviário", "Terminal portuário",
  "Porto", "Heliporto", "Heliponto", "Garagem", "Garagem operacional", "Edifício-garagem", "Centro de controle",
  "Estação de tratamento", "Central de resíduos", "Ecoponto", "Subestação",
  // Urban and landscape
  "Praça", "Parque", "Parque urbano", "Parque linear", "Jardim", "Jardim residencial", "Jardim botânico",
  "Jardim sensorial", "Pátio", "Terraço", "Rooftop", "Mirante", "Calçadão", "Passeio público", "Orla", "Boulevard",
  "Alameda", "Largo", "Passeio comercial", "Loteamento", "Bairro planejado", "Condomínio urbanístico", "Distrito",
  "Complexo de uso misto",
  // Parts of a building, rooms
  "Fachada", "Hall", "Lobby", "Recepção", "Portaria", "Guarita", "Área comum", "Sala de estar", "Sala de jantar",
  "Sala de TV", "Cozinha", "Copa", "Despensa", "Suíte", "Quarto", "Quarto infantil", "Quarto de bebê", "Closet",
  "Banheiro", "Lavabo", "Área de serviço", "Home office", "Sala de reunião", "Varanda", "Sacada", "Área externa",
  "Jardim de inverno", "Escada", "Anexo", "Edícula", "Cozinha gourmet", "Área gourmet", "Espaço gourmet externo",
  "Suíte master", "Banheiro social", "Quarto de hóspedes", "Ambiente", "Ambientes integrados",
  // Kinds of work (Fabio, 18 Oct 2026: a name starting with one leads with it too)
  "Reforma", "Retrofit", "Interiores",
];

/** Lowercase, without accents, for comparing. */
const plain = (text: string) =>
  text
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase();

// Longest first, so "Casa de praia" wins over "Casa".
const KNOWN = [...new Set(TYPES.map(plain))].sort((a, b) => b.length - a.length);

/** The title's lead and the rest, as written (whitespace tidied). */
export function splitTitle(name: string): { lead: string; rest: string } {
  // One form per accented letter, so positions in the plain copy match the text's.
  const words = name.normalize("NFC").trim().split(/\s+/).filter(Boolean);
  const text = words.join(" ");
  const folded = plain(text);
  for (const type of KNOWN) {
    // A whole-words match: the name is the type, or the type and then a space.
    if (folded === type || folded.startsWith(`${type} `)) {
      return { lead: text.slice(0, type.length), rest: text.slice(type.length).trim() };
    }
  }
  return { lead: words[0] ?? "", rest: words.slice(1).join(" ") };
}
